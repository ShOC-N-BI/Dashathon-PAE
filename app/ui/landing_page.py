# Landing Page
# app/ui/landing_page.py
# python -m app.main

from dash import html, dcc, Input, Output, State, callback, no_update, ctx, ALL, set_props, register_page

register_page(__name__, path="/nothing", name="Nothing")

# MARK: layout()
def layout():
    return html.Div(className="page-center", children=[
        html.P("There's nothing here...")
    ])

