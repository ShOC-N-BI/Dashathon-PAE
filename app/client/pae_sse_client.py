"""
app/client/pae_sse_client.py

Persistent SSE listener for the /paeinputs-sse stream.

The orchestrator emits named events in this format:

    event: PaeInputCreated
    data: {"paeInput": {"gbcId": "...", "requestId": "...", "trackId": "...", "originator": "..."}}

This module:
  1. Opens a long-lived GET connection to /paeinputs-sse in a daemon thread.
  2. Parses each event: / data: line-pair into a typed PaeInputCreated object.
  3. Dispatches to a registered handler so the rest of the app can react
     (e.g. forward to downstream services, update internal state, log, etc.).
  4. Reconnects automatically on any error with a short back-off.

Usage — call start() once at app startup (see app/main.py):

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

from config.settings import settings
from schemas.pae_schemas import PaeInputCreated

log = logging.getLogger(__name__)

# Handler type:  receives a fully-validated PaeInputCreated, returns nothing.
EventHandler = Callable[[PaeInputCreated], None]


class PaeSseClient:
    """Singleton-style SSE listener for the PAE input stream."""

    _thread:    threading.Thread | None = None
    _handler:   EventHandler | None    = None
    _running:   bool                   = False

    # Shared state readable by the Dash UI
    _ui_queue: thread_queue.Queue = thread_queue.Queue(maxsize=200)
    _status:   dict               = {"connected": False, "error": None}

    # ── Public API ─────────────────────────────────────────────────────────

    @classmethod
    def start(cls, on_event: EventHandler) -> None:
        """
        Start the background listener thread (idempotent — safe to call
        multiple times; only one thread is ever running).

        Args:
            on_event: Called once per PaeInputCreated event received from the
                      SSE stream. Runs on the listener thread, so keep it fast
                      or hand off work to a queue if needed.
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
        log.info("PaeSseClient started → %s/paeinputs-sse", settings.ORCHESTRATOR_BASE_URL)

    @classmethod
    def stop(cls) -> None:
        """Signal the listener loop to exit on next iteration."""
        cls._running = False

    # ── Internal ───────────────────────────────────────────────────────────

    @classmethod
    def _listen_loop(cls) -> None:
        """Runs on the daemon thread. Reconnects automatically on failure."""
        url = f"{settings.ORCHESTRATOR_BASE_URL}/paeinputs-sse"

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
                            "X-API-Key": settings.ORCHESTRATOR_API_KEY,
                        },
                    ) as resp:
                        resp.raise_for_status()
                        cls._status["connected"] = True
                        log.info("PaeSseClient connected")
                        cls._process_stream(resp)

            except Exception as exc:
                cls._status["connected"] = False
                cls._status["error"]     = str(exc)
                log.warning("PaeSseClient disconnected: %s — retrying in 3 s", exc)
                time.sleep(3)

        log.info("PaeSseClient stopped")

    @classmethod
    def _process_stream(cls, resp: httpx.Response) -> None:
        """
        Parse the SSE line stream.  Named events arrive as two consecutive
        non-blank lines:

            event: PaeInputCreated
            data: {"paeInput": {...}}

        We accumulate the event name from the `event:` line, then act when we
        see the matching `data:` line.  A blank line (the SSE message
        separator) resets state.  Comment lines (`: heartbeat`) are ignored.
        """
        current_event: str | None = None

        for line in resp.iter_lines():
            if not cls._running:
                break

            # Blank line — SSE message separator, reset state
            if not line:
                current_event = None
                continue

            # Comment / heartbeat
            if line.startswith(":"):
                continue

            if line.startswith("event:"):
                current_event = line[len("event:"):].strip()

            elif line.startswith("data:"):
                raw = line[len("data:"):].strip()
                cls._dispatch(current_event, raw)
                current_event = None  # reset after a complete pair

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

        # Always enqueue for the UI live feed regardless of schema validity
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
