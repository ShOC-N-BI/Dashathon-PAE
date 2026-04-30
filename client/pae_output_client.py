import json
from client.http_client import get_http_client
from schemas.pae_schemas import PaeOutput


def submit(pae: PaeOutput) -> PaeOutput:
    """
    POST a completed PAE assessment to the orchestrator.
    This is the primary output path — called after every AI assessment
    for both IRC messages (Path 1) and SSE reassessments (Path 2).
    """
    payload = json.loads(pae.model_dump_json(by_alias=True, exclude_none=True))

    # -- DEBUG: print what we are actually sending so we can spot schema mismatches
    print(f"SUBMITTING TO ORCHESTRATOR:\n{json.dumps(payload, indent=2)}")

    with get_http_client() as http:
        r = http.post("/paeoutputs", json=payload)

        if r.status_code == 422:
            # Print the full validation error body from the orchestrator
            print(f"ORCHESTRATOR REJECTED (422) — detail:\n{json.dumps(r.json(), indent=2)}")
            r.raise_for_status()

        r.raise_for_status()
        return PaeOutput.model_validate(r.json())


def get_by_id(pae_id: str) -> PaeOutput | None:
    """Fetch an existing PAE output by ID from the orchestrator."""
    with get_http_client() as http:
        r = http.get(f"/paeoutputs/{pae_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return PaeOutput.model_validate(r.json())


def update(pae_id: str, pae: PaeOutput) -> PaeOutput:
    """Update an existing PAE output by ID."""
    payload = json.loads(pae.model_dump_json(by_alias=True, exclude_none=True))
    with get_http_client() as http:
        r = http.put(f"/paeoutputs/{pae_id}", json=payload)

        if r.status_code == 422:
            print(f"ORCHESTRATOR REJECTED (422) — detail:\n{json.dumps(r.json(), indent=2)}")
            r.raise_for_status()

        r.raise_for_status()
        return PaeOutput.model_validate(r.json())