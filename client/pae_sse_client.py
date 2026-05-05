"""
client/pae_sse_client.py

Persistent SSE listener for the orchestrator's /paeinputs-sse stream.

The orchestrator emits named events in this format:

    event: PaeInputCreated
    data: {"paeInput": {"gbcId": "...", "requestId": "...", "trackId": "...", "originator": "..."}}

This module:
  1. Opens a long-lived GET connection to /paeinputs-sse in a daemon thread.
  2. Parses each event:/data: line-pair into a typed PaeInputCreated object.
  3. Dispatches to a registered handler so main.py can react.
  4. Reconnects automatically on any error with a short back-off.

Usage — call start() once at app startup (in main.py):

    from client.pae_sse_client import PaeSseClient
    PaeSseClient.start(on_event=my_handler)
"""

import json
import logging
import queue as thread_queue
import threading
import time
from typing import Callable

import httpx
import pae_config as config

from schemas.pae_schemas import PaeInputCreated

log = logging.getLogger(__name__)

# Handler type: receives a fully-validated PaeInputCreated, returns nothing.
EventHandler = Callable[[PaeInputCreated], None]


class PaeSseClient:
    """Singleton-style SSE listener for the PAE input stream."""

    _thread:  threading.Thread | None = None
    _handler: EventHandler | None     = None
    _running: bool                    = False

    # Shared state readable by the dashboard
    _ui_queue: thread_queue.Queue = thread_queue.Queue(maxsize=200)
    _status:   dict               = {"connected": False, "error": None}

    # ── Public API ─────────────────────────────────────────────────────────

    @classmethod
    def start(cls, on_event: EventHandler) -> None:
        """
        Start the background SSE listener thread.
        Idempotent — safe to call multiple times, only one thread runs.
        """
        if cls._thread and cls._thread.is_alive():
            log.warning("PaeSseClient already running — ignoring duplicate start()")
            return

        cls._handler = on_event
        cls._running = True
        cls._thread  = threading.Thread(
            target=cls._listen_loop,
            daemon=True,
            name="pae-sse-client",
        )
        cls._thread.start()
        log.info("PaeSseClient started → %s/paeinputs-sse", config.ORCHESTRATOR_BASE_URL)

    @classmethod
    def stop(cls) -> None:
        """Signal the listener loop to exit on next iteration."""
        cls._running = False

    @classmethod
    def status(cls) -> dict:
        """Return current connection status for the dashboard."""
        return cls._status

    # ── Internal ───────────────────────────────────────────────────────────

    @classmethod
    def _listen_loop(cls) -> None:
        """Runs on the daemon thread. Reconnects automatically on failure."""
        url = f"{config.ORCHESTRATOR_BASE_URL}/paeinputs-sse"

        while cls._running:
            try:
                cls._status["connected"] = False
                cls._status["error"]     = None
                log.info("PaeSseClient connecting to %s", url)

                with httpx.Client(timeout=None) as client:
                    with client.stream(
                        "GET", url,
                        headers={
                            "Accept":    "text/event-stream",
                            "X-API-Key": config.ORCHESTRATOR_API_KEY,
                        },
                    ) as resp:
                        resp.raise_for_status()
                        cls._status["connected"] = True
                        log.info("PaeSseClient connected")
                        cls._process_stream(resp)

            except Exception as exc:
                cls._status["connected"] = False
                cls._status["error"]     = str(exc)
                log.warning("PaeSseClient disconnected: %s — retrying in %ss", exc, config.SSE_RETRY_DELAY)
                time.sleep(config.SSE_RETRY_DELAY)

        log.info("PaeSseClient stopped")

    @classmethod
    def _process_stream(cls, resp: httpx.Response) -> None:
        """
        Parse the SSE line stream.

        Named events arrive as two consecutive non-blank lines:
            event: PaeInputCreated
            data: {"paeInput": {...}}

        A blank line is the SSE message separator and resets state.
        Comment lines (`: heartbeat`) are ignored.
        """
        current_event: str | None = None

        for line in resp.iter_lines():
            if not cls._running:
                break

            if not line:                        # blank line — end of SSE event
                current_event = None
                continue

            if line.startswith(":"):            # SSE comment/heartbeat — ignore
                continue

            if line.startswith("event:"):
                current_event = line[len("event:"):].strip()

            elif line.startswith("data:"):
                raw = line[len("data:"):].strip()
                cls._dispatch(current_event, raw)
                current_event = None

    @classmethod
    def _dispatch(cls, event_name: str | None, raw_data: str) -> None:
        """Parse raw JSON, push to the UI queue, and call the registered handler."""
        if event_name != "PaeInputCreated":
            log.debug("PaeSseClient ignoring unknown event: %s", event_name)
            return

        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            log.error("PaeSseClient failed to parse data: %s — %s", raw_data, exc)
            return

        # Always enqueue for the dashboard UI regardless of schema validity
        try:
            cls._ui_queue.put_nowait({"event": event_name, "data": payload})
        except thread_queue.Full:
            pass

        try:
            event = PaeInputCreated.model_validate(payload)
        except Exception as exc:
            log.error("PaeSseClient schema validation failed: %s — %s", payload, exc)
            return

        log.info(
            "PaeSseClient → PaeInputCreated  requestId=%s  trackId=%s  originator=%s",
            event.pae_input.request_id,
            event.pae_input.track_id,
            event.pae_input.originator,
        )

        if cls._handler:
            try:
                cls._handler(event)
            except Exception as exc:
                log.error("PaeSseClient handler raised: %s", exc)
