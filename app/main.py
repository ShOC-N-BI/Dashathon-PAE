# app/main.py

from pathlib import Path
import dash
import dash_bootstrap_components as dbc

app = dash.Dash(
    __name__,
    use_pages=True,
    pages_folder=str(Path(__file__).parent / "ui"),
    external_stylesheets=[dbc.themes.BOOTSTRAP],
)

# ── Import pages AFTER app is instantiated ─────────────────────────────────
from ui import pae_test  # noqa: F401, E402

# ── Layout ─────────────────────────────────────────────────────────────────
app.layout = dbc.Container(
    [
        dbc.NavbarSimple(
            children=[
                dbc.NavItem(dbc.NavLink("PAE Test", href="/pae-test"))
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
    print("\n── Registered pages ──")
    for page in dash.page_registry.values():
        print(f"  {page['name']} → {page['path']}")
    print("─────────────────────\n")
    app.run(debug=True, port=8050)