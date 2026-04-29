import logging

from schemas.pae_schemas import PaeOutput, PaeInput, PaeInputCreated
from config.settings import settings
import client.pae_output_client as output_client
import client.pae_input_client  as input_client

log = logging.getLogger(__name__)


# ── SSE event handler ──────────────────────────────────────────────────────

def on_pae_input_created(event: PaeInputCreated) -> None:
    """
    Called by PaeSseClient whenever a PaeInputCreated event arrives on the
    /paeinputs-sse stream.
 
    The SSE event IS the trigger — this handler acknowledges receipt and
    hands off to downstream processing (e.g. generating a PaeOutput).
    It must NOT call retrigger_pae, which POSTs back to /paeinputs on the
    same orchestrator, causing the orchestrator to re-broadcast the SSE
    event and loop indefinitely regardless of environment.
 
    retrigger_pae exists for a different scenario: when the PAE service
    itself needs to initiate a brand-new request to the orchestrator,
    not in response to an inbound SSE event.
    """
    pae_in = event.pae_input
    log.info(
        "PAE input received via SSE — requestId=%s  trackId=%s  gbcId=%s  originator=%s",
        pae_in.request_id,
        pae_in.track_id,
        pae_in.gbc_id,
        pae_in.originator,
    )
 
    # ── Downstream processing goes here ───────────────────────────────────
    def generate_pae_output(pae_in: PaeInput) -> PaeOutput:
        from datetime import datetime, timezone
        return PaeOutput(
            id=f"pae-{pae_in.request_id}",
            label="Auto-generated from SSE trigger",
            description=f"Generated for requestId={pae_in.request_id}",
            requestId=pae_in.request_id,
            gbcId=pae_in.gbc_id,
            entitiesOfInterest=[pae_in.track_id] if pae_in.track_id else [],
            battleEntity=[],
            battleEffects=[],
            chat=[],
            isDone=False,
            originator=pae_in.originator,
            lastUpdated=datetime.now(timezone.utc),
    )

    # The event has been received once. Add logic to act on it, such as:
    # result = generate_pae_output(pae_in)
    # output_client.submit(result)
    
    log.info(
        "PAE input acknowledged — ready for downstream processing  requestId=%s",
        pae_in.request_id,
    )


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
    """
    Initiates a brand-new PAE input request to the orchestrator.
    Use this when the PAE service needs to start a new request on its own,
    NOT in response to an inbound SSE event.
    """
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