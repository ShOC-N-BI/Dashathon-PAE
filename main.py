import logging
import threading
import requests
import pae_config as config

from ai.agent import get_battle_assessment
from client.pae_sse_client import PaeSseClient
from client.pae_output_client import submit as submit_pae_output
from irc.listener import start as irc_start
from output import log_writer
from pipeline.builder import make_request_id
from pipeline.filter import is_clean
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
    if not is_clean(message):
        live.update(make_dashboard(message, username, None, "FILTERED (NOISE)", source))
        return

    live.update(make_dashboard(message, username, None, "THINKING...", source))

    # -- Step 1: AI assessment → raw battle JSON dict
    # Read provider config fresh from .env on every call so live UI
    # changes (port 8080) take effect immediately without a restart.
    ai = config.get_ai_config()
    print(f"USING PROVIDER: {ai['provider'].upper()}  MODEL: {ai['model']}  URL: {ai['url']}  KEY_SET: {bool(ai['api_key'])}")

    tactical_json = get_battle_assessment(
        msg_content=message,
        username=username,
        request_id=request_id,
        lm_url=ai["url"],
        lm_model=ai["model"],
        timeout=ai["timeout"],
        provider=ai["provider"],
        api_key=ai["api_key"],
    )

    # -- Step 2: Write to local log (always, regardless of orchestrator availability)
    log_writer.write(tactical_json)

    # -- Step 3: Forward to config server dashboard (fire and forget)
    try:
        tactical_json[0]["_source"] = source
        requests.post("http://config:8080/assessment", json=tactical_json, timeout=2)
    except Exception:
        pass  # Dashboard is optional — never block the pipeline

    # -- Step 4: Validate against PaeOutput schema and POST to orchestrator
    record = tactical_json[0]
    try:
        pae_output = PaeOutput.model_validate(record)
        submit_pae_output(pae_output)
        submit_status = "SUBMITTED"
    except Exception as e:
        console.log(f"[red]Failed to submit to orchestrator: {e}[/red]")
        submit_status = "SUBMIT FAILED"

    # -- Step 5: Update dashboard
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
    )


# ---------------------------------------------------------------------------
# PATH 2 — SSE reassessment handler
# ---------------------------------------------------------------------------

def on_sse_event(live: Live, event: PaeInputCreated) -> None:
    """
    Called by PaeSseClient for every PaeInputCreated event from the orchestrator.

    The trackId field carries the message text to reassess.
    The requestId and originator come directly from the SSE payload.
    """
    pae = event.pae_input

    message = pae.track_id  # trackId IS the message text for reassessment

    if not message:
        console.log("[yellow]SSE event received with empty trackId — skipping.[/yellow]")
        return

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
            f"[bold cyan]AI Provider:[/bold cyan]  {config.AI_PROVIDER.upper()}\n"
            f"[bold cyan]Model:[/bold cyan]        {config.NANOGPT_MODEL if config.AI_PROVIDER == 'nanogpt' else config.LM_MODEL}\n"
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

        # -- Main thread stays alive and handles shutdown
        try:
            irc_thread.join()
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Shutting down PAE.[/bold yellow]")
            PaeSseClient.stop()
        except Exception as e:
            console.print(Panel(f"[bold red]CRITICAL ERROR:[/bold red] {e}"))
