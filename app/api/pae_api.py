import json
import logging
import uuid
from datetime import datetime, timezone

from app.config.settings import settings
from app.schemas.pae_schemas import PaeOutput, PaeInput, PaeInputCreated, PaeEffect
import app.client.pae_output_client as output_client
import app.client.pae_input_client  as input_client
from app.client.http_client import get_http_client

log = logging.getLogger(__name__)


# ── SSE event handler ──────────────────────────────────────────────────────

def on_pae_input_created(event: PaeInputCreated) -> None:
    """
    Called by PaeSseClient whenever a PaeInputCreated event arrives.

    Flow:
      1. Generate a PaeOutput from the incoming PaeInput
      2. POST the PaeOutput to the orchestrator (/paeoutputs)
      3. POST the PaeOutput to the orchestrator's /mefinput so the
         orchestrator can notify MEF — PAE does not call MEF directly.
    """
    pae_in = event.pae_input
    log.info(
        "PAE input received via SSE — requestId=%s  trackId=%s  gbcId=%s  originator=%s",
        pae_in.request_id,
        pae_in.track_id,
        pae_in.gbc_id,
        pae_in.originator,
    )

    try:
        # Step 1 — generate output
        result = generate_pae_output(pae_in)

        # Step 2 — submit to orchestrator
        submitted = output_client.submit(result)
        log.info(
            "PaeOutput submitted to orchestrator — id=%s  requestId=%s",
            submitted.id,
            submitted.request_id,
        )

        # Step 3 — notify orchestrator's /mefinput with the PaeOutput
        # NOTE: IN Production, the following will be ignored.  This is for testing only.
        if settings.ENVIRONMENT == "local":
            envelope = {
                "paeOutput": json.loads(
                    submitted.model_dump_json(by_alias=True, exclude_none=True)
                )
            }
            with get_http_client() as http:
                r = http.post("/mefinput", json=envelope)
                r.raise_for_status()
                log.info(
                    "PaeOutput forwarded to /mefinput — paeOutputId=%s",
                    submitted.id,
                )

    except Exception as exc:
        log.error("Error processing PaeInputCreated: %s", exc)


# ── PaeOutput generator (stub) ─────────────────────────────────────────────

def generate_pae_output(pae_in: PaeInput) -> PaeOutput:
    """
    Stub implementation — builds a minimal valid PaeOutput from a PaeInput.
    Replace the body of this function with real logic as the project matures.
    The function signature and return type should stay the same.
    """
    effect_id = str(uuid.uuid4())[:8]
    return PaeOutput(
        id=None,  # orchestrator assigns the ID on POST
        label="Auto-generated from SSE trigger",
        description=f"PaeOutput generated for requestId={pae_in.request_id}",
        requestId=pae_in.request_id,
        gbcId=pae_in.gbc_id,
        entitiesOfInterest=[pae_in.track_id] if pae_in.track_id else [],
        battleEntity=[],
        battleEffects=[
            PaeEffect(
                id=effect_id,
                effectOperator="Pending",
                description="Effect to be determined by mission planning.",
                timeWindow="TBD",
                stateHypothesis="Awaiting analysis.",
                opsLimits=[],
                goalContributions=[],
                recommended=False,
                ranking=None,
            )
        ],
        chat=[f"Auto-generated from SSE trigger — requestId={pae_in.request_id}"],
        isDone=False,
        originator=pae_in.originator,
        lastUpdated=datetime.now(timezone.utc),
    )


# ── REST service functions ─────────────────────────────────────────────────

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