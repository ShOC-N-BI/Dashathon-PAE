import logging
import threading
import requests
import pae_config as config

from ai.agent import get_battle_assessment
from client.pae_sse_client import PaeSseClient
from client.pae_output_client import submit as submit_pae_output
from irc.listener import start as irc_start
from output import log_writer, db_writer, gbc_api_client
from pipeline.builder import make_request_id
from pipeline.triage import is_relevant
from pipeline.enricher import classify, extract_context, fetch_track
from schemas.pae_schemas import PaeInputCreated, PaeOutput

from datetime import datetime
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

logging.basicConfig(level=logging.INFO)
console = Console()

# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------

def make_dashboard(
    last_msg:  str   = None,
    last_user: str   = None,
    verbs:     tuple = None,
    status:    str   = "LISTENING",
    source:    str   = "—",
) -> Table:
    table = Table(
        title="📡  PAE — Pre-emptive Action Engine",
        expand=True,
        show_lines=True,
    )
    table.add_column("Time",                        style="cyan",        no_wrap=True)
    table.add_column("Source",                      style="magenta")
    table.add_column("Message",                     style="green")
    table.add_column("AI Assessment (E01|E02|E03)", style="bold yellow")
    table.add_column("Status",                      style="bold blue")

    if last_msg:
        verb_str = " | ".join(verbs) if verbs else "—"
        table.add_row(
            datetime.now().strftime("%H:%M:%S"),
            f"{source} / {last_user or '?'}",
            last_msg[:80] + ("…" if len(last_msg) > 80 else ""),
            verb_str,
            status,
        )
    else:
        table.add_row("—", "—", "Waiting for traffic...", "—", "LISTENING")

    return table


# ---------------------------------------------------------------------------
# SHARED AI PIPELINE
# Called identically for both Path 1 (IRC) and Path 2 (SSE reassessment)
# ---------------------------------------------------------------------------

def run_pipeline(
    live:       Live,
    message:    str,
    username:   str,
    source:     str,
    request_id: str,
    gbc_id:     str | None = None,
    channel:    str | None = None,
) -> None:
    """
    Run the full PAE pipeline for one message:
        filter → AI → validate schema → POST to orchestrator → log

    Parameters
    ----------
    message    : Raw J-chat message text to assess.
    username   : Originator label (IRC nick or SSE originator field).
    source     : "IRC" or "SSE" — shown in the dashboard.
    request_id : Unique track ID for this assessment.
    gbc_id     : Optional GBC ID from the SSE trigger (None for IRC messages).
    """
    live.update(make_dashboard(message, username, None, "TRIAGING...", source))

    # -- Step 1: Read AI config fresh from .env (allows live UI switching)
    ai = config.get_ai_config()

    # -- Step 2: Triage — AI decides if message is tactically relevant
    # Fail-open: if triage errors or times out, message passes through
    if not is_relevant(
        message=message,
        triage_url=ai["triage_url"],
        triage_model=ai["triage_model"],
        api_key=ai["api_key"],
        timeout=ai["triage_timeout"],
    ):
        live.update(make_dashboard(message, username, None, "FILTERED — NOT TACTICAL", source))
        return

    live.update(make_dashboard(message, username, None, "THINKING...", source))
    print(f"USING PROVIDER: {ai['provider'].upper()}  MODEL: {ai['model']}  URL: {ai['url']}  KEY_SET: {bool(ai['api_key'])}")

    # -- Step 3: Enrich message with classify API (callsigns + entities)
    enriched = {}  # always defined — populated only if CLASSIFY_API_URL is set
    if config.CLASSIFY_API_URL:
        classification = classify(
            message=message,
            channel=channel if channel else config.IRC_CHANNEL.split(",")[0].strip(),
            sender=username,
            timestamp=__import__("datetime").datetime.utcnow().strftime("%H:%M:%S"),
            api_url=config.CLASSIFY_API_URL,
            timeout=config.CLASSIFY_TIMEOUT,
        )
        enriched = extract_context(classification)
        print(f"ENRICH: callsigns={enriched['callsigns']}  entities={enriched['entities']}")
        # Forward classify response to config server dashboard
        try:
            requests.post("http://config:8080/classify-log", json=classification, timeout=2)
        except Exception:
            pass

    # -- Step 4: Full AI assessment
    tactical_json = get_battle_assessment(
        msg_content=message,
        username=username,
        request_id=request_id,
        lm_url=ai["url"],
        lm_model=ai["model"],
        timeout=ai["timeout"],
        provider=ai["provider"],
        api_key=ai["api_key"],
        enriched=enriched,
        gbc_id=gbc_id,
    )

    # -- Step 2: Write to local log (always, regardless of orchestrator availability)
    log_writer.write(tactical_json)

    # -- Step 3: Write to database (only if DB credentials are configured in .env)
    if config.DB_HOST and config.DB_NAME and config.DB_USER and config.DB_PASSWORD:
        db_writer.insert(
            tactical_json,
            db_host=config.DB_HOST,
            db_name=config.DB_NAME,
            db_user=config.DB_USER,
            db_password=config.DB_PASSWORD,
            db_port=config.DB_PORT,
        )
    else:
        print("INFO: DB not configured — skipping database write.")

    # -- Step 4: Push to GBC API (only if GBC_API_URL is configured in .env)
    if config.GBC_API_URL:
        gbc_api_client.push(tactical_json, api_url=config.GBC_API_URL)
    else:
        print("INFO: GBC_API_URL not configured — skipping GBC push.")

    # -- Step 5: Forward to config server dashboard (fire and forget)
    try:
        tactical_json[0]["_source"] = source
        requests.post("http://config:8080/assessment", json=tactical_json, timeout=2)
    except Exception:
        pass  # Dashboard is optional — never block the pipeline

    # -- Step 6: Validate against PaeOutput schema and POST to orchestrator
    record = tactical_json[0]
    try:
        pae_output = PaeOutput.model_validate(record)
        submit_pae_output(pae_output)
        submit_status = "SUBMITTED"
    except Exception as e:
        console.log(f"[red]Failed to submit to orchestrator: {e}[/red]")
        submit_status = "SUBMIT FAILED"

    # -- Step 7: Update dashboard
    effects  = record.get("battleEffects", [])
    verbs    = tuple(e.get("effectOperator", "?") for e in effects[:3])
    label    = record.get("label", "?")
    live.update(make_dashboard(
        message, username, verbs,
        f"{submit_status} — {label}",
        source,
    ))


# ---------------------------------------------------------------------------
# PATH 1 — IRC handler
# ---------------------------------------------------------------------------

def on_irc_message(live: Live, username: str, message: str) -> None:
    """Called by irc.listener for every incoming J-chat message."""
    run_pipeline(
        live=live,
        message=message,
        username=username,
        source="IRC",
        request_id=make_request_id(),
        gbc_id=None,
        channel=config.IRC_CHANNEL.split(",")[0].strip(),
    )


# ---------------------------------------------------------------------------
# PATH 2 — SSE reassessment handler
# ---------------------------------------------------------------------------

def on_sse_event(live: Live, event: PaeInputCreated) -> None:
    """
    Called by PaeSseClient for every PaeInputCreated event from the orchestrator.

    The trackId field carries the message text to reassess.
    Before running the AI pipeline, the track ID is validated against the
    Track API. If the API returns empty or no data the retrigger is rejected —
    there is no point assessing a message with no associated track data.

    The requestId and originator come directly from the SSE payload.
    """
    pae = event.pae_input

    message = pae.track_id  # trackId IS the message text for reassessment

    if not message:
        console.log("[yellow]SSE: empty trackId — skipping.[/yellow]")
        live.update(make_dashboard(
            message or "—", pae.originator, None,
            "REJECTED — NO TRACK ID", "SSE"
        ))
        return

    # -- Step 1: Format check — reject anything that doesn't look like a track number
    # Valid track IDs start with TN followed by digits (e.g. TN700, TN044)
    # Plain numbers like 44250, IRC timestamps, or other noise are rejected here
    import re as _re
    if not _re.match(r'^TN\d+$', message.strip().upper()):
        console.log(f"[yellow]SSE: '{message}' is not a valid track number format — rejecting.[/yellow]")
        live.update(make_dashboard(
            message, pae.originator, None,
            "REJECTED — INVALID TRACK FORMAT", "SSE"
        ))
        return

    # -- Step 2: Validate track against Track API
    if config.TRACK_API_URL:
        live.update(make_dashboard(message, pae.originator, None, "VALIDATING TRACK...", "SSE"))
        track_data = fetch_track(
            track_id=message.strip().upper(),
            api_url=config.TRACK_API_URL,
            timeout=config.TRACK_API_TIMEOUT,
        )
        if track_data is None:
            console.log(f"[yellow]SSE: track '{message}' not found — rejecting retrigger.[/yellow]")
            live.update(make_dashboard(
                message, pae.originator, None,
                "REJECTED — NO TRACK DATA", "SSE"
            ))
            return
        console.log(f"[green]SSE: track '{message}' validated — proceeding to assessment.[/green]")
    else:
        # TRACK_API_URL not configured — log warning but allow through
        console.log(f"[yellow]SSE: TRACK_API_URL not set — skipping track validation for '{message}'.[/yellow]")

    run_pipeline(
        live=live,
        message=message,
        username=pae.originator,
        source="SSE",
        request_id=pae.request_id,
        gbc_id=pae.gbc_id,
    )


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    console.print(
        Panel(
            f"[bold cyan]IRC:[/bold cyan]          {config.IRC_SERVER}:{config.IRC_PORT}  {config.IRC_CHANNEL}\n"
            f"[bold cyan]Orchestrator:[/bold cyan] {config.ORCHESTRATOR_BASE_URL or 'NOT CONFIGURED'}\n"
            f"[bold cyan]AI Endpoint:[/bold cyan]  {config.AI_ENDPOINT}\n"
            f"[bold cyan]Model:[/bold cyan]        {config.AI_MODEL}\n"
            f"[bold cyan]DB:[/bold cyan]           {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}",
            title="PAE — Pre-emptive Action Engine",
            border_style="cyan",
        )
    )

    with Live(make_dashboard(), refresh_per_second=4, console=console) as live:

        # -- Path 1: IRC listener in a background thread
        irc_thread = threading.Thread(
            target=irc_start,
            kwargs={
                "server":     config.IRC_SERVER,
                "port":       config.IRC_PORT,
                "channel":    config.IRC_CHANNEL,
                "nickname":   config.IRC_NICKNAME or None,
                "on_message": lambda user, msg: on_irc_message(live, user, msg),
            },
            name="irc-listener",
            daemon=True,
        )
        irc_thread.start()

        # -- Path 2: SSE listener via PaeSseClient (starts its own thread)
        if config.ORCHESTRATOR_BASE_URL:
            PaeSseClient.start(
                on_event=lambda event: on_sse_event(live, event)
            )
        else:
            console.print("[yellow]ORCHESTRATOR_BASE_URL not set — SSE listener not started.[/yellow]")

        # -- Main thread stays alive indefinitely regardless of IRC/SSE state
        # Using an Event instead of irc_thread.join() so the app never exits
        # if IRC drops or fails to connect — it will keep retrying in the background
        try:
            stop_event = threading.Event()
            stop_event.wait()  # blocks forever until KeyboardInterrupt
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Shutting down PAE.[/bold yellow]")
            PaeSseClient.stop()
        except Exception as e:
            console.print(Panel(f"[bold red]CRITICAL ERROR:[/bold red] {e}"))