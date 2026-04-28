from schemas.pae_schemas import PaeOutput, PaeInput, PaeInputCreated
import client.pae_output_client as output_client
import client.pae_input_client  as input_client


def fetch_all_pae() -> list[PaeOutput]:
    return output_client.get_all()


def fetch_pae_by_id(pae_id: str) -> PaeOutput | None:
    return output_client.get_by_id(pae_id)


def submit_pae(pae: PaeOutput) -> PaeOutput:
    return output_client.submit(pae)


def update_pae(pae_id: str, pae: PaeOutput) -> PaeOutput:
    return output_client.update(pae_id, pae)


def retrigger_pae(
    request_id: str,
    originator: str,
    gbc_id:     str | None = None,
    track_id:   str | None = None,
) -> dict:
    pae_input = PaeInput(
        requestId=request_id,
        originator=originator,
        gbcId=gbc_id,
        trackId=track_id,
    )
    return input_client.retrigger(pae_input)


def submit_pae_input_created(
    request_id: str,
    originator: str,
    gbc_id:     str | None = None,
    track_id:   str | None = None,
) -> dict:
    pae_input = PaeInput(
        requestId=request_id,
        originator=originator,
        gbcId=gbc_id,
        trackId=track_id,
    )
    pae_input_created = PaeInputCreated(paeInput=pae_input)
    return input_client.submit_pae_input(pae_input_created)