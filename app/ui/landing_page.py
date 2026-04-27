from dash import html
import app.services.DataResponse as dr

def layout():
    messages = dr.get_messages()
    
    processed_elements = []
    for msg in messages[:8]:  # Slightly more messages since the box is thicker
        air, intel, cyber = dr.extracted_chat(msg)
        if air or intel or cyber:
            processed_elements.append(html.Div([
                html.P(f"Raw: {msg}", style={'fontSize': '11px', 'color': '#666', 'margin': '0'}),
                html.Div([
                    html.Span(f"Air: {', '.join(air)} ", className="badge-air", style={'marginRight': '5px'}) if air else None,
                    html.Span(f"Intel: {', '.join(intel)} ", className="badge-intel", style={'marginRight': '5px'}) if intel else None,
                    html.Span(f"Cyber: {', '.join(cyber)} ", className="badge-cyber") if cyber else None,
                ], style={'marginBottom': '12px'})
            ]))

    return html.Div(className="page-center", style={'maxWidth': '900px', 'margin': '0 auto', 'padding': '20px'}, children=[
        html.H2("PAE J-Chat Data", style={'textAlign': 'center', 'marginBottom': '25px', 'fontFamily': 'sans-serif'}),

        # --- REVISED DATA BOX (Thicker) ---
        html.Div(className="main-data-box", children=[
            html.Div(
                processed_elements, 
                style={
                    'backgroundColor': '#f8f9fa', 
                    'padding': '20px', 
                    'borderRadius': '10px', 
                    'height': '100px',       # Increased height for a "thicker" look
                    'overflowY': 'auto',     
                    'border': '2px solid #dee2e6',
                    'width': '100%',
                    'boxSizing': 'border-box'
                }
            )
        ], style={'marginBottom': '35px'}),

        # --- WIDER ACTION BUTTONS ---
        html.Div(className="action-bar", children=[
            html.Button("ACTION 1", id="btn-1", n_clicks=0, style=get_button_style()),
            html.Button("ACTION 2", id="btn-2", n_clicks=0, style=get_button_style()),
            html.Button("ACTION 3", id="btn-3", n_clicks=0, style=get_button_style()),
        ], style={
            'display': 'flex', 
            'justifyContent': 'center', 
            'gap': '30px', 
            'marginBottom': '50px'
        }),

        # --- SUBMIT BUTTON ---
        html.Div([
            html.Button("SUBMIT REPORT", id="submit-val", n_clicks=0, 
                style={
                    'width': '70%',          # Submit button is now centered and specific width
                    'margin': '0 auto',
                    'display': 'block',
                    'padding': '18px', 
                    'fontWeight': 'bold', 
                    'fontSize': '16px',
                    'backgroundColor': '#1a1a1a',
                    'color': 'white',
                    'border': 'none',
                    'borderRadius': '6px',
                    'cursor': 'pointer',
                    'boxShadow': '0 4px 6px rgba(0,0,0,0.1)'
                })
        ])
    ])

# Helper function for consistent wide button styling
def get_button_style():
    return {
        'minWidth': '180px',        # Ensures they are wider even with short text
        'padding': '20px 30px',      # Added horizontal padding for width
        'fontSize': '14px',
        'fontWeight': 'bold',
        'border': '2px solid #007bff',
        'backgroundColor': 'white',
        'color': "#023973",
        'borderRadius': '8px',
        'cursor': 'pointer',
        'transition': '0.3s'
    }