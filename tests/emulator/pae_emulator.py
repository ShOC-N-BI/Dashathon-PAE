import json
import sys
import os
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from app.schemas.pae_schemas import PaeOutput, PaeInputCreated

# ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

app = FastAPI(title="PAE Emulator", version="1.0.0")


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
def submit_pae(pae: PaeOutput):
    if pae.id is None:
        pae.id = f"pae-{len(_pae_store) + 1:03d}"
    _pae_store[pae.id] = _to_store(pae)
    return _pae_store[pae.id]


@app.put("/paeoutputs/{pae_id}", response_model=PaeOutput)
def update_pae(pae_id: str, pae: PaeOutput):
    if pae_id not in _pae_store:
        raise HTTPException(status_code=404, detail=f"PAE {pae_id} not found")
    _pae_store[pae_id] = _to_store(pae)
    return _pae_store[pae_id]



# ── PAE Input endpoint ─────────────────────────────────────────────────────

@app.post("/paeinputs", status_code=202)
def submit_pae_input(pae_input_created: PaeInputCreated):
    return {
        "status":     "accepted",
        "requestId":  pae_input_created.pae_input.request_id,
        "gbcId":      pae_input_created.pae_input.gbc_id,
        "trackId":    pae_input_created.pae_input.track_id,
        "originator": pae_input_created.pae_input.originator,
    }