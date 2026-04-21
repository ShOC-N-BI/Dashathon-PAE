# Main
# app/main.py

import dash
from dash import html, dcc, Input, Output, callback

from app.ui.landing_page import layout as landing_layout

app = dash.Dash(__name__, title=" GBC", suppress_callback_exceptions=True)

app.layout = html.Div(className = "app-wrapper", children = [
    dcc.Location(id="url"),
    html.Div(id="page-content"),
])

# ---- ROUTER ----
@callback(
    Output("page-content", "children"),
    Input("url", "pathname")
)
def render_page(pathname):
    print("Router called: " + pathname)

    if pathname == "/":
        return landing_layout()

    return html.H2("404 - Page not found")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8070)
