from app.client.http_client import get_http_client
from app.schemas.pae_schemas import PaeInput, PaeInputCreated


def retrigger(pae_input: PaeInput) -> dict:
    with get_http_client() as http:
        r = http.post(
            "/paeinputs",
            json=pae_input.model_dump(by_alias=True, exclude_none=True)
        )
        r.raise_for_status()
        return r.json()


def submit_pae_input(pae_input_created: PaeInputCreated) -> dict:
    with get_http_client() as http:
        r = http.post(
            "/paeinputs",
            json=pae_input_created.model_dump(by_alias=True, exclude_none=True)
        )
        r.raise_for_status()
        return r.json()