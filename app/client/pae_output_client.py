import json
from app.client.http_client import get_http_client
from app.schemas.pae_schemas import PaeOutput


def get_all() -> list[PaeOutput]:
    with get_http_client() as http:
        r = http.get("/paeoutputs")
        r.raise_for_status()
        return [PaeOutput.model_validate(item) for item in r.json()]


def get_by_id(pae_id: str) -> PaeOutput | None:
    with get_http_client() as http:
        r = http.get(f"/paeoutputs/{pae_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return PaeOutput.model_validate(r.json())


def submit(pae: PaeOutput) -> PaeOutput:
    with get_http_client() as http:
        r = http.post(
            "/paeoutputs",
            json=json.loads(pae.model_dump_json(by_alias=True, exclude_none=True))
        )
        r.raise_for_status()
        return PaeOutput.model_validate(r.json())


def update(pae_id: str, pae: PaeOutput) -> PaeOutput:
    with get_http_client() as http:
        r = http.put(
            f"/paeoutputs/{pae_id}",
            json=json.loads(pae.model_dump_json(by_alias=True, exclude_none=True))
        )
        r.raise_for_status()
        return PaeOutput.model_validate(r.json())