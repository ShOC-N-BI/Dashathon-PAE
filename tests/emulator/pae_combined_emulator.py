"""
tests/emulator/pae_combined_emulator.py

Single-server emulator that matches the production orchestrator topology —
all PAE endpoints served on one port, exactly as a real orchestrator would.

Endpoints:
    GET  /paeoutputs             — list all PAE outputs
    GET  /paeoutputs/{id}        — get PAE output by ID
    POST /paeoutputs             — submit a PAE output
    PUT  /paeoutputs/{id}        — update a PAE output
    POST /paeinputs              — accept a PAE input trigger, broadcast to SSE
    GET  /paeinputs-sse          — SSE stream of PaeInputCreated named events

Run with:
    python -m tests.emulator.pae_run_combined_emulator

This is the primary emulator for everyday development.  The separate
pae_output_emulator.py and pae_sse_emulator.py are kept only for isolated
unit testing of each concern independently.
"""

import asyncio
import json
import logging
import sys
import os
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
import httpx
from app.schemas.pae_schemas import PaeOutput, PaeInput, PaeInputCreated
from app.config.settings import settings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

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


# ── In-memory store ────────────────────────────────────────────────────────
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
                "effectOperator":  "Suppress",
                "description":     "Jam radar emissions using EA aircraft.",
                "timeWindow":      "Immediate",
                "stateHypothesis": "Radar emissions will be disrupted.",
                "opsLimits": [
                    {
                        "description":     "EA asset must be on station.",
                        "battleEntity":    "EA-18G",
                        "stateHypothesis": "Within jamming range."
                    }
                ],
                "goalContributions": [{"battleGoal": "1.2.a", "effect": "high"}],
                "recommended": True,
                "ranking":     1,
            }
        ],
        "chat":        ["Radar emissions detected at PB2.1."],
        "isDone":      False,
        "originator":  "rhino",
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
    },
    "pae-002": {
        "id":          "pae-002",
        "label":       "Imminent Ballistic Missile Launch",
        "description": "TBM Type 1 launch preparations detected at PB1.2.",
        "requestId":   "0101-12 d",
        "gbcId":       None,
        "entitiesOfInterest": ["TGT-TBM-001"],
        "battleEntity":       ["TBM Type 1"],
        "battleEffects": [
            {
                "id":              "pae-002-e01",
                "effectOperator":  "Destroy",
                "description":     "Strike launch bunker with precision-guided munitions.",
                "timeWindow":      "Pre-emptive",
                "stateHypothesis": "Launch facility destroyed.",
                "opsLimits": [
                    {
                        "description":     "Target coordinates must be CAT 1.",
                        "battleEntity":    "Stealth Bomber",
                        "stateHypothesis": "TBM still on ground at impact."
                    }
                ],
                "goalContributions": [{"battleGoal": "2.1.c", "effect": "high"}],
                "recommended": True,
                "ranking":     1,
            }
        ],
        "chat":        ["TBM launch preparations detected at PB1.2."],
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
    if pae.id is None:
        pae.id = f"pae-{len(_pae_store) + 1:03d}"
    _pae_store[pae.id] = _to_store(pae)
    log.info("PAE emulator stored paeOutput id=%s", pae.id)
 
    if settings.ENVIRONMENT == "local":
        envelope = {"paeOutput": _pae_store[pae.id]}
        async with httpx.AsyncClient() as client:
            try:
                log.info("PAE emulator forwarding to %s/mefinput", settings.MEF_BASE_URL)
                r = await client.post(
                    f"{settings.MEF_BASE_URL}/mefinput",
                    json=envelope,
                    timeout=5.0,
                )
                log.info("MEF forward response: %s", r.status_code)
            except Exception as exc:
                log.error("PAE emulator failed to forward to MEF: %s", exc)
 
    return _pae_store[pae.id]
 
 
@app.put("/paeoutputs/{pae_id}", response_model=PaeOutput)
async def update_pae(pae_id: str, pae: PaeOutput):
    if pae_id not in _pae_store:
        raise HTTPException(status_code=404, detail=f"PAE {pae_id} not found")
    _pae_store[pae_id] = _to_store(pae)
    log.info("PAE emulator updated paeOutput id=%s", pae_id)
 
    if settings.ENVIRONMENT == "local":
        envelope = {"paeOutput": _pae_store[pae_id]}
        async with httpx.AsyncClient() as client:
            try:
                log.info("PAE emulator forwarding to %s/mefinput", settings.MEF_BASE_URL)
                r = await client.post(
                    f"{settings.MEF_BASE_URL}/mefinput",
                    json=envelope,
                    timeout=5.0,
                )
                log.info("MEF forward response: %s", r.status_code)
            except Exception as exc:
                log.error("PAE emulator failed to forward to MEF: %s", exc)
 
    return _pae_store[pae_id]


# ── PAE Input endpoint ─────────────────────────────────────────────────────

@app.post("/paeinputs", status_code=202)
async def submit_pae_input(request: Request):
    """
    Accepts a PAE input trigger and broadcasts it to all SSE subscribers.

    Accepts two shapes:
      - PaeInputCreated envelope: {"paeInput": {...}}
      - Raw PaeInput:             {"requestId": ..., "originator": ...}
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


# ── SSE endpoint ───────────────────────────────────────────────────────────

@app.get("/paeinputs-sse")
async def paeinputs_sse(request: Request):
    """
    SSE stream — emits PaeInputCreated whenever POST /paeinputs is called.

        event: PaeInputCreated
        data: {"paeInput": {"gbcId": "...", "requestId": "...", "trackId": "...", "originator": "..."}}

    Heartbeat every 15 s to keep connections alive:
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


# ── MEF forwarding endpoint ────────────────────────────────────────────────
# This endpoint is for testing only — in production the real orchestrator handles
# this routing internally.  In the emulator we forward explicitly so the two
# services remain independent — PAE only talks to port 3016, MEF only talks to port 3027.

@app.post("/mefinput", status_code=201)
async def forward_to_mef(request: Request):
    """
    Receives a PaeOutputCreatedOrUpdated envelope from the PAE microservice
    and forwards it to the MEF emulator on MEF_BASE_URL.

    In production the real orchestrator handles this routing internally.
    In the emulator we forward explicitly so the two services remain
    independent — PAE only talks to port 3016, MEF only talks to port 3027.
    """
    body = await request.json()
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{settings.MEF_BASE_URL}/mefinput",
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()