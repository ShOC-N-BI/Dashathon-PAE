"""
tests/emulator/pae_combined_emulator.py

Single-server emulator that matches the production orchestrator topology.
All PAE endpoints served on one port, exactly as a real orchestrator would.

Endpoints:
    GET  /paeoutputs             — list all PAE outputs
    GET  /paeoutputs/{id}        — get PAE output by ID
    POST /paeoutputs             — submit a PAE output (your app calls this)
    PUT  /paeoutputs/{id}        — update a PAE output
    POST /paeinputs              — fire a reassessment trigger → broadcasts to SSE
    GET  /paeinputs-sse          — SSE stream your app listens to

Run with:
    python tests/emulator/pae_run_emulator.py

To test a reassessment trigger, POST to /paeinputs:
    curl -X POST http://127.0.0.1:3016/paeinputs \
      -H "Content-Type: application/json" \
      -d '{
            "requestId": "test-001",
            "trackId": "AMTI SAT has detected activity consistent with TBM launch at PB1.2",
            "originator": "test-operator"
          }'

Your PAE app will receive the SSE event, run the AI, and POST the result
back to /paeoutputs. Check http://127.0.0.1:3016/paeoutputs to see it.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from schemas.pae_schemas import PaeOutput, PaeInput, PaeInputCreated
import config

log = logging.getLogger(__name__)
app = FastAPI(title="PAE Emulator", version="1.0.0")

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


# ── In-memory store (pre-loaded with two example records) ─────────────────
_pae_store: dict[str, dict] = {
    "pae-001": {
        "id":          "pae-001",
        "label":       "Hostile Radar Detected",
        "description": "Early warning radar active at grid PB2.1.",
        "requestId":   "0101-01",
        "gbcId":       None,
        "entitiesOfInterest": ["TGT-RAD-001"],
        "battleEntity":       ["SA-10 Radar"],
        "battleEffects": [
            {
                "id":              "pae-001-e01",
                "effectOperator":  "SUPPRESS",
                "description":     "Jam radar emissions using EA aircraft.",
                "timeWindow":      "Immediate",
                "stateHypothesis": "Radar emissions will be disrupted.",
                "opsLimits": [
                    {
                        "description":     "EA asset must be on station.",
                        "battleEntity":    "EA-18G",
                        "stateHypothesis": "Within jamming range.",
                    }
                ],
                "goalContributions": [{"battleGoal": "1.2.a", "effect": "high"}],
                "recommended": True,
                "ranking":     1,
            }
        ],
        "chat":        ["Radar emissions detected at PB2.1.", "PAE generated for pre-emptive and defensive options."],
        "isDone":      False,
        "originator":  "rhino",
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
    },
    "pae-002": {
        "id":          "pae-002",
        "label":       "Imminent Ballistic Missile Launch",
        "description": "TBM Type 1 launch preparations detected at PB1.2.",
        "requestId":   "0101-12",
        "gbcId":       None,
        "entitiesOfInterest": ["TGT-TBM-001", "PB1.2"],
        "battleEntity":       ["TBM Type 1"],
        "battleEffects": [
            {
                "id":              "pae-002-e01",
                "effectOperator":  "DESTROY",
                "description":     "Strike launch bunker with precision-guided munitions.",
                "timeWindow":      "Pre-emptive",
                "stateHypothesis": "Launch facility destroyed.",
                "opsLimits": [
                    {
                        "description":     "Target coordinates must be CAT 1.",
                        "battleEntity":    "Stealth Bomber",
                        "stateHypothesis": "TBM still on ground at impact.",
                    }
                ],
                "goalContributions": [{"battleGoal": "2.1.c", "effect": "high"}],
                "recommended": True,
                "ranking":     1,
            }
        ],
        "chat":        ["TBM launch preparations detected at PB1.2.", "PAE generated for pre-emptive and defensive options."],
        "isDone":      False,
        "originator":  "rhino",
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
    },
}


def _to_store(pae: PaeOutput) -> dict:
    return json.loads(pae.model_dump_json(by_alias=True))


# ── PAE Output endpoints ───────────────────────────────────────────────────

@app.get("/paeoutputs", response_model=list[PaeOutput])
def get_all_pae():
    return list(_pae_store.values())


@app.get("/paeoutputs/{pae_id}", response_model=PaeOutput)
def get_pae(pae_id: str):
    if pae_id not in _pae_store:
        raise HTTPException(status_code=404, detail=f"PAE {pae_id} not found")
    return _pae_store[pae_id]


@app.post("/paeoutputs", response_model=PaeOutput, status_code=201)
async def submit_pae(pae: PaeOutput):
    """Your PAE app POSTs its AI assessment here."""
    if pae.id is None:
        pae.id = f"pae-{len(_pae_store) + 1:03d}"
    _pae_store[pae.id] = _to_store(pae)
    log.info("Emulator stored paeOutput id=%s  label=%s", pae.id, pae.label)
    return _pae_store[pae.id]


@app.put("/paeoutputs/{pae_id}", response_model=PaeOutput)
async def update_pae(pae_id: str, pae: PaeOutput):
    if pae_id not in _pae_store:
        raise HTTPException(status_code=404, detail=f"PAE {pae_id} not found")
    _pae_store[pae_id] = _to_store(pae)
    log.info("Emulator updated paeOutput id=%s", pae_id)
    return _pae_store[pae_id]


# ── PAE Input endpoint ─────────────────────────────────────────────────────

@app.post("/paeinputs", status_code=202)
async def submit_pae_input(request: Request):
    """
    Fire a reassessment trigger. Broadcasts a PaeInputCreated SSE event
    to all connected listeners (including your PAE app).

    Accepts two shapes:
      - PaeInputCreated envelope: { "paeInput": { "requestId", "trackId", "originator" } }
      - Raw PaeInput:             { "requestId", "trackId", "originator" }

    The trackId should contain the message text you want reassessed.
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

    log.info(
        "Emulator broadcast PaeInputCreated — requestId=%s  trackId=%s",
        event.pae_input.request_id,
        event.pae_input.track_id,
    )

    return {
        "status":     "accepted",
        "requestId":  event.pae_input.request_id,
        "gbcId":      event.pae_input.gbc_id,
        "trackId":    event.pae_input.track_id,
        "originator": event.pae_input.originator,
    }


# ── SSE endpoint ───────────────────────────────────────────────────────────

@app.get("/paeinputs-sse")
async def paeinputs_sse(request: Request):
    """
    Your PAE app connects here to receive reassessment triggers.
    Emits a PaeInputCreated event whenever POST /paeinputs is called.
    Sends a heartbeat comment every 15s to keep the connection alive.
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
