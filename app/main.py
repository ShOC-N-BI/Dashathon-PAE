# app/main.py

import logging
from pathlib import Path
import dash
import dash_bootstrap_components as dbc
from threading import Thread
from tests.emulator.pae_run_emulator import run_emulator
emulator = Thread(target=run_emulator, args=())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)

app = dash.Dash(
    __name__,
    use_pages=True,
    pages_folder=str(Path(__file__).parent / "ui"),
    external_stylesheets=[dbc.themes.BOOTSTRAP],
)

# ── Import pages AFTER app is instantiated ─────────────────────────────────
# from ui import pae_test  # noqa: F401, E402

# ── Start SSE listener ─────────────────────────────────────────────────────
# PaeSseClient opens a persistent connection to /paeinputs-sse on the
# orchestrator and calls on_pae_input_created for every named event received.
from app.client.pae_sse_client import PaeSseClient   # noqa: E402
from app.api.pae_api import on_pae_input_created      # noqa: E402

PaeSseClient.start(on_event=on_pae_input_created)

# ── Layout ─────────────────────────────────────────────────────────────────
app.layout = dbc.Container(
    [
        dbc.NavbarSimple(
            children=[
                dbc.NavItem(dbc.NavLink("PAE Test", href="/")),
                dbc.NavItem(dbc.NavLink("landing_page.py", href="/nothing")),
                dbc.NavItem(dbc.NavLink("Emulator Docs", href="http://localhost:3016/docs")),
            ],
            brand="Dashathon",
            color="primary",
            dark=True,
            className="mb-3",
        ),
        dash.page_container,
    ],
    fluid=True,
)

if __name__ == "__main__":
    try:
        emulator.start()
        print("\n── Registered pages ──")
        for page in dash.page_registry.values():
            print(f"  {page['name']} → {page['path']}")
        print("─────────────────────\n")
        app.run(debug=True, port=8050, host="0.0.0.0")
    finally:
        if emulator.is_alive():
            emulator.join()