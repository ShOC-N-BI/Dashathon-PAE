"""
tests/emulator/pae_sse_emulator.py

Emulates the external orchestrator's SSE stream.
Runs on port 3017 — this is what SSE_BASE_URL points to.

Endpoints:
    POST /paeinputs          — accepts a PaeInput trigger, broadcasts it to SSE
    GET  /paeinputs-sse      — SSE stream of PaeInputCreated named events

This server is intentionally separate from pae_output_emulator.py to mirror
the real architecture: in production, the SSE stream originates from an
external orchestrator, not from within the PAE microservice itself.

Testing flow:
    1. Start pae_output_emulator.py  (port 3016) — REST store
    2. Start pae_sse_emulator.py     (port 3017) — SSE trigger source
    3. Start the PAE Dash app        (port 8050)
    4. In the Dash UI, POST /paeinputs on the SSE emulator to fire a trigger.
       The microservice PaeSseClient will receive it and call retrigger_pae,
       which POSTs to /paeinputs on the OUTPUT emulator — a clean, separate call.
"""

import asyncio
import json
import sys
import os
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from app.schemas.pae_schemas import PaeInput, PaeInputCreated

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

app = FastAPI(title="PAE SSE Emulator", version="1.0.0")

# ── SSE subscriber registry ────────────────────────────────────────────────
_sse_subscribers: list[asyncio.Queue] = []


def _broadcast_pae_input(pae_input_dict: dict) -> None:
    """Emit a PaeInputCreated named event to all connected SSE subscribers."""
    payload = (
        f"event: PaeInputCreated\n"
        f"data: {json.dumps(pae_input_dict)}\n\n"
    )
    dead: list[asyncio.Queue] = []
    for q in _sse_subscribers:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _sse_subscribers.remove(q)


@app.post("/paeinputs", status_code=202)
async def submit_pae_input(request: Request):
    """
    Accepts a PAE input trigger and broadcasts it to all SSE subscribers.

    Accepts two shapes:
      - PaeInputCreated envelope: {"paeInput": {...}}
      - Raw PaeInput:             {"requestId": ..., "originator": ...}

    This endpoint does NOT forward to the output emulator — it only
    broadcasts the SSE event.  The microservice handles the retrigger.
    """
    body = await request.json()

    if "paeInput" in body:
        event = PaeInputCreated.model_validate(body)
    else:
        pae_input = PaeInput.model_validate(body)
        event     = PaeInputCreated(paeInput=pae_input)

    _broadcast_pae_input(
        {"paeInput": event.model_dump(by_alias=True)["paeInput"]}
    )

    return {
        "status":     "accepted",
        "requestId":  event.pae_input.request_id,
        "gbcId":      event.pae_input.gbc_id,
        "trackId":    event.pae_input.track_id,
        "originator": event.pae_input.originator,
    }


@app.get("/paeinputs-sse")
async def paeinputs_sse(request: Request):
    """
    SSE stream — emits PaeInputCreated whenever POST /paeinputs is called.

        event: PaeInputCreated
        data: {"paeInput": {"gbcId": "...", "requestId": "...", "trackId": "...", "originator": "..."}}

    Heartbeat every 15 s:
        : heartbeat
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _sse_subscribers.append(queue)

    async def event_generator():
        try:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield message
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"

                if await request.is_disconnected():
                    break
        finally:
            if queue in _sse_subscribers:
                _sse_subscribers.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )