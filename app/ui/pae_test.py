import json
import queue as thread_queue
from datetime import datetime, timezone
from dash import dcc, html, callback, Input, Output, State, register_page
import dash_bootstrap_components as dbc
from config.settings import settings
from api.pae_api import (
    fetch_all_pae,
    fetch_pae_by_id,
    submit_pae,
    update_pae,
    submit_pae_input_created,
)
from schemas.pae_schemas import PaeOutput

# Re-use the single SSE connection that main.py already started via
# PaeSseClient.  The UI drains the same queue the microservice logic uses,
# so there is exactly one persistent connection to /paeinputs-sse.
from client.pae_sse_client import PaeSseClient

register_page(__name__, path="/pae-test", name="PAE Test")

# ── Default payloads ───────────────────────────────────────────────────────
DEFAULT_PAE_OUTPUT = json.dumps(
    {
        "id":          "pae-003",
        "label":       "Hostile Air Defense Activation",
        "description": "SA-15 battery has gone active at grid PA3.4.",
        "requestId":   "0101-13",
        "gbcId":       None,
        "entitiesOfInterest": ["TGT-AD-001"],
        "battleEntity":       ["SA-15 Gauntlet"],
        "battleEffects": [
            {
                "id":              "pae-003-e01",
                "effectOperator":  "Suppress",
                "description":     "Suppress SA-15 radar with EA aircraft.",
                "timeWindow":      "Immediate",
                "stateHypothesis": "Air defense radar will be disrupted.",
                "opsLimits": [
                    {
                        "battleEntity":    "EA-18G",
                        "description":     "EA asset must be on station.",
                        "stateHypothesis": "Within jamming range.",
                    }
                ],
                "goalContributions": [{"battleGoal": "1.1.a", "effect": "high"}],
                "recommended": True,
                "ranking":     1,
            }
        ],
        "chat":        ["SA-15 battery active at PA3.4."],
        "isDone":      False,
        "originator":  "rhino",
        "lastUpdated": "2026-04-16T22:53:11.206811+00:00",
    },
    indent=2,
)

DEFAULT_PAE_INPUT = json.dumps(
    {
        "paeInput": {
            "gbcId":      "gbc-002-e03-3",
            "requestId":  "0101-12",
            "trackId":    "6",
            "originator": "AFRL",
        }
    },
    indent=2,
)

DEFAULT_UPDATE_ID = "pae-002"


# ── Helpers ────────────────────────────────────────────────────────────────
def _pre_style(height: int) -> dict:
    return {
        "height":       f"{height}px",
        "overflowY":    "auto",
        "background":   "var(--bs-light)",
        "padding":      "12px",
        "borderRadius": "4px",
        "fontSize":     "13px",
    }


def _editor_row(
    textarea_id, default, submit_id, submit_label,
    reset_id, response_id, badge_id,
):
    return dbc.Row(
        [
            dbc.Col(
                [
                    html.Label("Request payload", className="fw-bold"),
                    dcc.Textarea(
                        id=textarea_id,
                        value=default,
                        style={"width": "100%", "height": "320px", "fontFamily": "monospace"},
                    ),
                    dbc.Button(submit_label, id=submit_id, color="primary",   className="mt-2 me-2"),
                    dbc.Button("Reset",      id=reset_id,  color="secondary", outline=True, className="mt-2"),
                ],
                width=6,
            ),
            dbc.Col(
                [
                    html.Label("Response", className="fw-bold"),
                    dcc.Loading(html.Pre(id=response_id, style=_pre_style(320))),
                    html.Div(id=badge_id, className="mt-2"),
                ],
                width=6,
            ),
        ]
    )


# ── Layout ─────────────────────────────────────────────────────────────────
layout = dbc.Container(
    [
        html.H4("PAE — API Test Page", className="my-3"),

        # Interval fires every second to drain the SSE queue into the live log
        dcc.Interval(id="pae-sse-interval", interval=1000, n_intervals=0),
        # Store holds the accumulated log entries
        dcc.Store(id="pae-sse-store", data=[]),

        dbc.Tabs(
            [
                # GET all
                dbc.Tab(
                    dbc.Card(
                        dbc.CardBody([
                            dbc.Button("GET /paeoutputs", id="pae-get-btn", color="success", className="mb-3"),
                            dcc.Loading(html.Pre(id="pae-get-response", style=_pre_style(380))),
                        ]),
                        className="mt-2",
                    ),
                    label="GET all",
                ),

                # GET by ID
                dbc.Tab(
                    dbc.Card(
                        dbc.CardBody([
                            dbc.InputGroup(
                                [
                                    dbc.InputGroupText("PAE ID"),
                                    dbc.Input(id="pae-get-id-input", placeholder="e.g. pae-001", value="pae-001"),
                                    dbc.Button("GET /paeoutputs/{id}", id="pae-get-id-btn", color="success"),
                                ],
                                className="mb-3",
                            ),
                            dcc.Loading(html.Pre(id="pae-get-id-response", style=_pre_style(340))),
                        ]),
                        className="mt-2",
                    ),
                    label="GET by ID",
                ),

                # POST output
                dbc.Tab(
                    dbc.Card(
                        dbc.CardBody([
                            _editor_row(
                                textarea_id="pae-post-payload",
                                default=DEFAULT_PAE_OUTPUT,
                                submit_id="pae-post-btn",
                                submit_label="POST /paeoutputs",
                                reset_id="pae-post-reset-btn",
                                response_id="pae-post-response",
                                badge_id="pae-post-badge",
                            )
                        ]),
                        className="mt-2",
                    ),
                    label="POST output",
                ),

                # PUT output
                dbc.Tab(
                    dbc.Card(
                        dbc.CardBody([
                            dbc.InputGroup(
                                [
                                    dbc.InputGroupText("PAE ID"),
                                    dbc.Input(id="pae-put-id-input", placeholder="e.g. pae-002", value=DEFAULT_UPDATE_ID),
                                ],
                                className="mb-2",
                            ),
                            _editor_row(
                                textarea_id="pae-put-payload",
                                default=DEFAULT_PAE_OUTPUT,
                                submit_id="pae-put-btn",
                                submit_label="PUT /paeoutputs/{id}",
                                reset_id="pae-put-reset-btn",
                                response_id="pae-put-response",
                                badge_id="pae-put-badge",
                            ),
                        ]),
                        className="mt-2",
                    ),
                    label="PUT output",
                ),

                # POST input
                dbc.Tab(
                    dbc.Card(
                        dbc.CardBody([
                            _editor_row(
                                textarea_id="pae-input-payload",
                                default=DEFAULT_PAE_INPUT,
                                submit_id="pae-input-btn",
                                submit_label="POST /paeinputs",
                                reset_id="pae-input-reset-btn",
                                response_id="pae-input-response",
                                badge_id="pae-input-badge",
                            )
                        ]),
                        className="mt-2",
                    ),
                    label="POST input",
                ),

                # SSE Live Feed
                dbc.Tab(
                    dbc.Card(
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    html.Div(id="pae-sse-status-badge", className="mb-2"),
                                    html.Small(
                                        f"Listening on {settings.ORCHESTRATOR_BASE_URL}/paeinputs-sse",
                                        className="text-muted",
                                    ),
                                ], width=8),
                                dbc.Col([
                                    dbc.Button(
                                        "Clear log",
                                        id="pae-sse-clear-btn",
                                        color="secondary",
                                        outline=True,
                                        size="sm",
                                        className="float-end",
                                    ),
                                ], width=4),
                            ], className="mb-2"),
                            html.Pre(
                                id="pae-sse-log",
                                style={
                                    **_pre_style(420),
                                    "whiteSpace": "pre-wrap",
                                    "wordBreak":  "break-all",
                                },
                            ),
                        ]),
                        className="mt-2",
                    ),
                    label="SSE Live Feed",
                ),
            ]
        ),
    ],
    fluid=True,
)


# ── Callbacks ──────────────────────────────────────────────────────────────

@callback(
    Output("pae-get-response", "children"),
    Input("pae-get-btn",       "n_clicks"),
    prevent_initial_call=True,
)
def get_all(_):
    try:
        records = fetch_all_pae()
        return json.dumps(
            [json.loads(r.model_dump_json(by_alias=True)) for r in records],
            indent=2,
        )
    except Exception as e:
        return f"Error:\n{e}"


@callback(
    Output("pae-get-id-response", "children"),
    Input("pae-get-id-btn",       "n_clicks"),
    State("pae-get-id-input",     "value"),
    prevent_initial_call=True,
)
def get_by_id(_, pae_id):
    if not pae_id:
        return "Enter a PAE ID."
    try:
        record = fetch_pae_by_id(pae_id)
        if not record:
            return f"No record found for ID: {pae_id}"
        return record.model_dump_json(by_alias=True, indent=2)
    except Exception as e:
        return f"Error:\n{e}"


@callback(
    Output("pae-post-payload",  "value"),
    Input("pae-post-reset-btn", "n_clicks"),
    prevent_initial_call=True,
)
def reset_post(_):
    return DEFAULT_PAE_OUTPUT


@callback(
    Output("pae-post-response", "children"),
    Output("pae-post-badge",    "children"),
    Input("pae-post-btn",       "n_clicks"),
    State("pae-post-payload",   "value"),
    prevent_initial_call=True,
)
def post_pae(_, payload_str):
    try:
        pae    = PaeOutput.model_validate(json.loads(payload_str))
        result = submit_pae(pae)
        return (
            result.model_dump_json(by_alias=True, indent=2),
            dbc.Badge("201 Created", color="success"),
        )
    except json.JSONDecodeError as e:
        return f"Invalid JSON:\n{e}", dbc.Badge("Invalid JSON", color="danger")
    except Exception as e:
        return f"Error:\n{e}", dbc.Badge("Error", color="danger")


@callback(
    Output("pae-put-payload",  "value"),
    Input("pae-put-reset-btn", "n_clicks"),
    prevent_initial_call=True,
)
def reset_put(_):
    return DEFAULT_PAE_OUTPUT


@callback(
    Output("pae-put-response", "children"),
    Output("pae-put-badge",    "children"),
    Input("pae-put-btn",       "n_clicks"),
    State("pae-put-id-input",  "value"),
    State("pae-put-payload",   "value"),
    prevent_initial_call=True,
)
def put_pae(_, pae_id, payload_str):
    if not pae_id:
        return "Enter a PAE ID.", dbc.Badge("Missing ID", color="warning")
    try:
        pae    = PaeOutput.model_validate(json.loads(payload_str))
        result = update_pae(pae_id, pae)
        return (
            result.model_dump_json(by_alias=True, indent=2),
            dbc.Badge("200 OK", color="success"),
        )
    except json.JSONDecodeError as e:
        return f"Invalid JSON:\n{e}", dbc.Badge("Invalid JSON", color="danger")
    except Exception as e:
        return f"Error:\n{e}", dbc.Badge("Error", color="danger")


@callback(
    Output("pae-input-payload",  "value"),
    Input("pae-input-reset-btn", "n_clicks"),
    prevent_initial_call=True,
)
def reset_input(_):
    return DEFAULT_PAE_INPUT


@callback(
    Output("pae-input-response", "children"),
    Output("pae-input-badge",    "children"),
    Input("pae-input-btn",       "n_clicks"),
    State("pae-input-payload",   "value"),
    prevent_initial_call=True,
)
def post_pae_input(_, payload_str):
    try:
        payload = json.loads(payload_str)
        pae_in  = payload.get("paeInput", payload)
        result  = submit_pae_input_created(
            request_id=pae_in["requestId"],
            originator=pae_in["originator"],
            gbc_id=pae_in.get("gbcId"),
            track_id=pae_in.get("trackId"),
        )
        return (
            json.dumps(result, indent=2),
            dbc.Badge("202 Accepted", color="success"),
        )
    except json.JSONDecodeError as e:
        return f"Invalid JSON:\n{e}", dbc.Badge("Invalid JSON", color="danger")
    except Exception as e:
        return f"Error:\n{e}", dbc.Badge("Error", color="danger")


# ── SSE live-feed callbacks ────────────────────────────────────────────────

@callback(
    Output("pae-sse-store",        "data"),
    Output("pae-sse-status-badge", "children"),
    Input("pae-sse-interval",      "n_intervals"),
    State("pae-sse-store",         "data"),
    prevent_initial_call=False,
)
def drain_sse_queue(_, existing_lines: list[str]):
    new_lines: list[str] = []
    while not PaeSseClient._ui_queue.empty():
        try:
            item       = PaeSseClient._ui_queue.get_nowait()
            event_name = item.get("event", "unknown")
            data       = item.get("data", {})
            ts         = datetime.now(timezone.utc).strftime("%H:%M:%S")

            if event_name == "PaeInputCreated" and isinstance(data, dict):
                pae_in     = data.get("paeInput", data)
                request_id = pae_in.get("requestId", "?")
                track_id   = pae_in.get("trackId",   "?")
                originator = pae_in.get("originator", "?")
                summary    = f"requestId={request_id}  trackId={track_id}  originator={originator}"
            else:
                summary = ""

            header = f"── {ts}  event={event_name}" + (f"  {summary}" if summary else "") + " ──"
            new_lines.append(header + "\n" + json.dumps(data, indent=2))

        except thread_queue.Empty:
            break

    updated = new_lines + (existing_lines or [])
    updated = updated[:100]

    if PaeSseClient._status["connected"]:
        badge = dbc.Badge("● Connected", color="success")
    elif PaeSseClient._status["error"]:
        badge = dbc.Badge(f"✕ {PaeSseClient._status['error'][:60]}", color="danger")
    else:
        badge = dbc.Badge("○ Connecting…", color="warning")

    return updated, badge


@callback(
    Output("pae-sse-log", "children"),
    Input("pae-sse-store", "data"),
)
def render_sse_log(lines: list[str]):
    if not lines:
        return "Waiting for events…"
    return "\n\n".join(lines)


@callback(
    Output("pae-sse-store",    "data",    allow_duplicate=True),
    Input("pae-sse-clear-btn", "n_clicks"),
    prevent_initial_call=True,
)
def clear_sse_log(_):
    return []