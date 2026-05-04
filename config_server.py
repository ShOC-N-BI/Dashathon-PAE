"""
config_server.py

Lightweight FastAPI server running on port 8080 inside the container.

Routes:
    GET  /                — config editor UI
    GET  /dashboard       — live assessment dashboard
    GET  /env             — current .env values as JSON
    POST /env             — write updated values to .env
    GET  /status          — current PAE runtime config
    POST /assessment      — main.py posts each completed assessment here
    GET  /assessments     — returns full history as JSON
    GET  /assessments/sse — SSE stream for live dashboard updates
"""

import json
import asyncio
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

ENV_PATH = Path(__file__).parent / ".env"

app = FastAPI(title="PAE Config Server", version="1.0.0")

# ---------------------------------------------------------------------------
# ASSESSMENT STORE  — keeps the last 200 assessments in memory
# ---------------------------------------------------------------------------

_assessments: deque = deque(maxlen=200)
_sse_subscribers: list[asyncio.Queue] = []


def _broadcast(record: dict) -> None:
    """Push a new assessment to all connected SSE dashboard clients."""
    payload = f"data: {json.dumps(record)}\n\n"
    dead = []
    for q in _sse_subscribers:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _sse_subscribers.remove(q)


# ---------------------------------------------------------------------------
# EDITABLE FIELDS
# ---------------------------------------------------------------------------

EDITABLE_FIELDS = {
    "ORCHESTRATOR_BASE_URL": {
        "label":       "Orchestrator Base URL",
        "description": "Base URL of the orchestrator cluster app",
        "placeholder": "http://10.5.185.XX:PORT",
        "type":        "url",
    },
    "ORCHESTRATOR_API_KEY": {
        "label":       "Orchestrator API Key",
        "description": "X-API-Key sent with every orchestrator request",
        "placeholder": "your-api-key-here",
        "type":        "password",
    },
    "AI_PROVIDER": {
        "label":       "AI Provider",
        "description": "Which AI backend to use: lmstudio or nanogpt",
        "placeholder": "lmstudio",
        "type":        "toggle",
        "options":     ["lmstudio", "nanogpt"],
    },
    "LM_STUDIO_URL": {
        "label":       "LM Studio URL",
        "description": "Full URL to the LM Studio completions endpoint",
        "placeholder": "http://10.5.185.55:4334/v1/chat/completions",
        "type":        "url",
    },
    "LM_MODEL": {
        "label":       "LM Studio Model",
        "description": "Model identifier (google/gemma-4-e4b or google/gemma-4-31b)",
        "placeholder": "google/gemma-4-e4b",
        "type":        "text",
    },
    "NANOGPT_API_KEY": {
        "label":       "NanoGPT API Key",
        "description": "Your NanoGPT API key (only used when AI_PROVIDER=nanogpt)",
        "placeholder": "sk-nano-...",
        "type":        "password",
    },
    "NANOGPT_MODEL": {
        "label":       "NanoGPT Model",
        "description": "Model to use via NanoGPT (e.g. gpt-4o, claude-3-5-sonnet)",
        "placeholder": "gpt-4o",
        "type":        "text",
    },
    "IRC_SERVER": {
        "label":       "IRC Server",
        "description": "IRC server hostname or IP",
        "placeholder": "10.5.185.72",
        "type":        "text",
    },
    "IRC_CHANNEL": {
        "label":       "IRC Channel",
        "description": "IRC channel to listen on",
        "placeholder": "#app_dev",
        "type":        "text",
    },
    "SSE_RETRY_DELAY": {
        "label":       "SSE Retry Delay (seconds)",
        "description": "How long to wait before reconnecting to the SSE stream",
        "placeholder": "5",
        "type":        "number",
    },
}

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def read_env() -> dict:
    values = {}
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


def write_env(updates: dict) -> None:
    lines = []
    updated_keys = set()
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                lines.append(line)
                continue
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if key in updates:
                lines.append(f"{key}={updates[key]}")
                updated_keys.add(key)
            else:
                lines.append(line)
    for key, val in updates.items():
        if key not in updated_keys:
            lines.append(f"{key}={val}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

# ---------------------------------------------------------------------------
# MODELS
# ---------------------------------------------------------------------------

class EnvUpdate(BaseModel):
    values: dict[str, str]

# ---------------------------------------------------------------------------
# ROUTES — config
# ---------------------------------------------------------------------------

@app.get("/env")
def get_env():
    current = read_env()
    result = {}
    for key, meta in EDITABLE_FIELDS.items():
        result[key] = {**meta, "value": current.get(key, "")}
    return JSONResponse(content=result)


@app.post("/env")
def update_env(body: EnvUpdate):
    safe = {k: v for k, v in body.values.items() if k in EDITABLE_FIELDS}
    if not safe:
        raise HTTPException(status_code=400, detail="No valid fields provided.")
    write_env(safe)
    return {"status": "saved", "updated": list(safe.keys())}


@app.post("/provider/{provider}")
def set_provider(provider: str):
    """Quick toggle endpoint — sets AI_PROVIDER directly."""
    if provider not in ("lmstudio", "nanogpt"):
        raise HTTPException(status_code=400, detail="Provider must be lmstudio or nanogpt.")
    write_env({"AI_PROVIDER": provider})
    return {"status": "saved", "AI_PROVIDER": provider}


@app.get("/status")
def get_status():
    current = read_env()
    return {
        "orchestrator": current.get("ORCHESTRATOR_BASE_URL", "NOT SET"),
        "model":        current.get("LM_MODEL", "NOT SET"),
        "irc_server":   current.get("IRC_SERVER", "NOT SET"),
        "irc_channel":  current.get("IRC_CHANNEL", "NOT SET"),
    }

# ---------------------------------------------------------------------------
# ROUTES — assessments
# ---------------------------------------------------------------------------

@app.post("/assessment")
async def receive_assessment(request: Request):
    """
    main.py POSTs every completed battle JSON record here.
    Stored in memory and broadcast to all live dashboard clients.
    """
    body = await request.json()
    record = body[0] if isinstance(body, list) else body
    record["_receivedAt"] = datetime.utcnow().isoformat() + "Z"
    _assessments.appendleft(record)
    _broadcast(record)
    return {"status": "received"}


@app.get("/assessments")
def get_assessments():
    """Return full assessment history as JSON."""
    return JSONResponse(content=list(_assessments))


@app.get("/assessments/sse")
async def assessments_sse(request: Request):
    """SSE stream — pushes each new assessment to connected dashboard clients."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _sse_subscribers.append(queue)

    async def generator():
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                if await request.is_disconnected():
                    break
        finally:
            if queue in _sse_subscribers:
                _sse_subscribers.remove(queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ---------------------------------------------------------------------------
# ROUTES — pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def serve_config():
    return HTMLResponse(content=CONFIG_HTML)


@app.get("/dashboard", response_class=HTMLResponse)
def serve_dashboard():
    return HTMLResponse(content=DASHBOARD_HTML)

# ---------------------------------------------------------------------------
# CONFIG UI HTML
# ---------------------------------------------------------------------------

CONFIG_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PAE Config</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Barlow:wght@300;400;600;700&display=swap');
    :root {
      --bg:#090d12;--surface:#0f1720;--border:#1a2940;--accent:#00e5ff;
      --accent2:#ff6b35;--text:#c8d8e8;--muted:#4a6080;--success:#00ff88;
      --error:#ff4466;--mono:'Share Tech Mono',monospace;--sans:'Barlow',sans-serif;
    }
    *{box-sizing:border-box;margin:0;padding:0;}
    body{background:var(--bg);color:var(--text);font-family:var(--sans);min-height:100vh;}
    body::before{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,229,255,.015) 2px,rgba(0,229,255,.015) 4px);pointer-events:none;z-index:1000;}
    header{background:var(--surface);border-bottom:1px solid var(--border);padding:20px 40px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;}
    .logo{display:flex;align-items:center;gap:14px;}
    .logo-badge{width:36px;height:36px;border:2px solid var(--accent);display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:13px;color:var(--accent);}
    .logo-text{font-size:13px;font-weight:600;letter-spacing:4px;text-transform:uppercase;color:var(--accent);}
    .logo-sub{font-size:11px;color:var(--muted);letter-spacing:2px;text-transform:uppercase;margin-top:2px;}
    nav{display:flex;gap:4px;}
    nav a{font-family:var(--mono);font-size:11px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);text-decoration:none;padding:8px 16px;border:1px solid transparent;transition:.2s;}
    nav a:hover{color:var(--accent);border-color:var(--border);}
    nav a.active{color:var(--accent);border-color:var(--accent);background:rgba(0,229,255,.05);}
    .status-dot{width:7px;height:7px;border-radius:50%;background:var(--success);animation:pulse 2s infinite;display:inline-block;}
    @keyframes pulse{0%,100%{opacity:1;}50%{opacity:.3;}}
    main{max-width:860px;margin:0 auto;padding:48px 40px;}
    .status-panel{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--accent);padding:20px 24px;margin-bottom:40px;display:grid;grid-template-columns:1fr 1fr;gap:12px 32px;}
    .status-item label{font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);font-family:var(--mono);}
    .status-item .val{font-family:var(--mono);font-size:12px;color:var(--accent);margin-top:4px;word-break:break-all;}
    .section-title{font-size:10px;letter-spacing:4px;text-transform:uppercase;color:var(--muted);font-family:var(--mono);margin-bottom:24px;display:flex;align-items:center;gap:12px;}
    .section-title::after{content:'';flex:1;height:1px;background:var(--border);}
    .fields{display:flex;flex-direction:column;gap:20px;margin-bottom:36px;}
    .field{display:grid;grid-template-columns:220px 1fr;gap:0 24px;align-items:start;padding:20px 24px;background:var(--surface);border:1px solid var(--border);transition:border-color .2s;}
    .field:hover{border-color:rgba(0,229,255,.3);}
    .field-meta label{font-size:12px;font-weight:600;color:var(--text);display:block;margin-bottom:6px;}
    .field-meta .desc{font-size:11px;color:var(--muted);line-height:1.5;}
    .field-input-wrap{position:relative;}
    .field input{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);font-family:var(--mono);font-size:12px;padding:10px 14px;outline:none;transition:.2s;}
    .field input:focus{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent);}
    .field input.modified{border-color:var(--accent2);box-shadow:0 0 0 1px var(--accent2);}
    .modified-tag{position:absolute;right:10px;top:50%;transform:translateY(-50%);font-size:9px;letter-spacing:2px;color:var(--accent2);font-family:var(--mono);text-transform:uppercase;pointer-events:none;}
    .actions{display:flex;gap:14px;align-items:center;}
    .btn-save{background:var(--accent);color:var(--bg);border:none;padding:12px 32px;font-family:var(--mono);font-size:12px;font-weight:700;letter-spacing:3px;text-transform:uppercase;cursor:pointer;transition:.15s;}
    .btn-save:hover{background:#33eeff;box-shadow:0 0 30px rgba(0,229,255,.3);}
    .btn-save:disabled{background:var(--muted);cursor:not-allowed;}
    .btn-reset{background:transparent;color:var(--muted);border:1px solid var(--border);padding:12px 24px;font-family:var(--mono);font-size:11px;letter-spacing:2px;text-transform:uppercase;cursor:pointer;transition:.15s;}
    .btn-reset:hover{border-color:var(--muted);color:var(--text);}
    .toast{position:fixed;bottom:32px;right:32px;padding:14px 24px;font-family:var(--mono);font-size:12px;letter-spacing:1px;border-left:3px solid var(--success);background:var(--surface);border-top:1px solid var(--border);border-right:1px solid var(--border);border-bottom:1px solid var(--border);transform:translateY(20px);opacity:0;transition:.3s;z-index:999;}
    .toast.show{transform:translateY(0);opacity:1;}
    .toast.error{border-left-color:var(--error);color:var(--error);}
    .toast.success{color:var(--success);}
    .warning-box{background:rgba(255,107,53,.08);border:1px solid rgba(255,107,53,.3);border-left:3px solid var(--accent2);padding:14px 20px;margin-bottom:32px;font-size:12px;color:var(--accent2);font-family:var(--mono);line-height:1.6;}
    .provider-switch{display:flex;align-items:center;gap:0;margin-bottom:40px;background:var(--surface);border:1px solid var(--border);width:fit-content;}
    .provider-switch-label{font-family:var(--mono);font-size:10px;letter-spacing:3px;text-transform:uppercase;color:var(--muted);padding:14px 20px;border-right:1px solid var(--border);}
    .provider-btn{font-family:var(--mono);font-size:12px;letter-spacing:2px;text-transform:uppercase;padding:14px 28px;border:none;cursor:pointer;transition:.15s;background:transparent;color:var(--muted);}
    .provider-btn.active-lm{background:var(--accent);color:var(--bg);font-weight:700;}
    .provider-btn.active-nano{background:var(--accent2);color:var(--bg);font-weight:700;}
    .provider-btn:hover:not(.active-lm):not(.active-nano){color:var(--text);background:rgba(255,255,255,.04);}
  </style>
</head>
<body>
<header>
  <div class="logo">
    <div class="logo-badge">PAE</div>
    <div><div class="logo-text">Config Manager</div><div class="logo-sub">Pre-emptive Action Engine</div></div>
  </div>
  <nav>
    <a href="/" class="active">Config</a>
    <a href="/dashboard">Dashboard</a>
  </nav>
</header>
<main>
  <div class="status-panel">
    <div class="status-item"><label>Orchestrator</label><div class="val" id="st-orchestrator">loading...</div></div>
    <div class="status-item"><label>Model</label><div class="val" id="st-model">loading...</div></div>
    <div class="status-item"><label>IRC Server</label><div class="val" id="st-irc">loading...</div></div>
    <div class="status-item"><label>IRC Channel</label><div class="val" id="st-channel">loading...</div></div>
  </div>
  <div class="provider-switch">
    <span class="provider-switch-label">AI ENGINE</span>
    <button class="provider-btn" id="btn-lm" onclick="setProvider('lmstudio')">⚡ LM Studio</button>
    <button class="provider-btn" id="btn-nano" onclick="setProvider('nanogpt')">☁ NanoGPT</button>
  </div>
  <div class="warning-box">⚠ Changes are written to .env immediately. Restart the container to force a full reload.</div>
  <div class="section-title">Configuration Fields</div>
  <div class="fields" id="fields"></div>
  <div class="actions">
    <button class="btn-save" id="btn-save" onclick="saveChanges()">Save Changes</button>
    <button class="btn-reset" onclick="resetForm()">Reset</button>
  </div>
</main>
<div class="toast" id="toast"></div>
<script>
  let originalValues={},fieldMeta={};
  async function loadEnv(){
    const res=await fetch('/env');const data=await res.json();fieldMeta=data;originalValues={};
    const container=document.getElementById('fields');container.innerHTML='';
    for(const[key,meta]of Object.entries(data)){
      originalValues[key]=meta.value;
      const t=meta.type==='password'?'password':'text';
      const f=document.createElement('div');f.className='field';
      f.innerHTML=`<div class="field-meta"><label>${meta.label}</label><div class="desc">${meta.description}</div></div><div class="field-input-wrap"><input type="${t}" id="field-${key}" data-key="${key}" value="${esc(meta.value)}" placeholder="${esc(meta.placeholder)}" oninput="onInput(this)" autocomplete="off"/><span class="modified-tag" id="tag-${key}" style="display:none">MODIFIED</span></div>`;
      container.appendChild(f);
    }
  }
  async function loadStatus(){
    try{const res=await fetch('/status');const d=await res.json();
      document.getElementById('st-orchestrator').textContent=d.orchestrator;
      document.getElementById('st-model').textContent=d.model;
      document.getElementById('st-irc').textContent=d.irc_server;
      document.getElementById('st-channel').textContent=d.irc_channel;
    }catch(e){}
  }
  function onInput(el){
    const key=el.dataset.key,tag=document.getElementById('tag-'+key);
    if(el.value!==originalValues[key]){el.classList.add('modified');tag.style.display='block';}
    else{el.classList.remove('modified');tag.style.display='none';}
  }
  function resetForm(){for(const key of Object.keys(originalValues)){const el=document.getElementById('field-'+key);if(el){el.value=originalValues[key];el.classList.remove('modified');document.getElementById('tag-'+key).style.display='none';}}}
  async function saveChanges(){
    const values={};let hasChanges=false;
    for(const key of Object.keys(originalValues)){const el=document.getElementById('field-'+key);if(el&&el.value!==originalValues[key]){values[key]=el.value;hasChanges=true;}}
    if(!hasChanges){showToast('No changes to save.',false);return;}
    const btn=document.getElementById('btn-save');btn.disabled=true;btn.textContent='Saving...';
    try{const res=await fetch('/env',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({values})});
      if(res.ok){const d=await res.json();showToast('Saved: '+d.updated.join(', '),true);await loadEnv();await loadStatus();}
      else showToast('Save failed.',false);
    }catch(e){showToast('Network error.',false);}
    btn.disabled=false;btn.textContent='Save Changes';
  }
  function showToast(msg,ok){const t=document.getElementById('toast');t.textContent=(ok?'✓  ':'✗  ')+msg;t.className='toast show '+(ok?'success':'error');setTimeout(()=>{t.className='toast';},3500);}
  function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
  async function setProvider(p){
    try{
      const res=await fetch('/provider/'+p,{method:'POST'});
      if(res.ok){
        showToast('Switched to '+p.toUpperCase(),true);
        updateProviderButtons(p);
      } else showToast('Switch failed.',false);
    }catch(e){showToast('Network error.',false);}
  }
  function updateProviderButtons(p){
    const lm=document.getElementById('btn-lm');
    const nano=document.getElementById('btn-nano');
    lm.className='provider-btn'+(p==='lmstudio'?' active-lm':'');
    nano.className='provider-btn'+(p==='nanogpt'?' active-nano':'');
  }
  async function loadProvider(){
    try{
      const res=await fetch('/env');
      const d=await res.json();
      const p=(d.AI_PROVIDER&&d.AI_PROVIDER.value)||'lmstudio';
      updateProviderButtons(p);
    }catch(e){}
  }
  loadEnv();loadStatus();loadProvider();setInterval(loadStatus,10000);
</script>
</body>
</html>"""

# ---------------------------------------------------------------------------
# DASHBOARD HTML
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PAE Dashboard</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;500;600;700&display=swap');
    :root{
      --bg:#060a0f;--surface:#0b1219;--surface2:#0f1a24;--border:#162030;
      --accent:#00e5ff;--accent2:#ff6b35;--accent3:#7fff6b;
      --text:#b8ccd8;--muted:#3a5060;--mono:'Share Tech Mono',monospace;
      --sans:'Rajdhani',sans-serif;
    }
    *{box-sizing:border-box;margin:0;padding:0;}
    body{background:var(--bg);color:var(--text);font-family:var(--sans);min-height:100vh;overflow-x:hidden;}
    body::before{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,229,255,.008) 3px,rgba(0,229,255,.008) 4px);pointer-events:none;z-index:1000;}

    header{background:var(--surface);border-bottom:1px solid var(--border);padding:16px 32px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;}
    .logo{display:flex;align-items:center;gap:12px;}
    .logo-badge{width:34px;height:34px;border:2px solid var(--accent);display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:12px;color:var(--accent);}
    .logo-text{font-size:14px;font-weight:700;letter-spacing:4px;text-transform:uppercase;color:var(--accent);}
    .logo-sub{font-size:10px;color:var(--muted);letter-spacing:2px;text-transform:uppercase;}
    nav{display:flex;gap:4px;}
    nav a{font-family:var(--mono);font-size:11px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);text-decoration:none;padding:8px 16px;border:1px solid transparent;transition:.2s;}
    nav a:hover{color:var(--accent);border-color:var(--border);}
    nav a.active{color:var(--accent);border-color:var(--accent);background:rgba(0,229,255,.05);}
    .live-badge{display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:11px;color:var(--accent3);}
    .dot{width:6px;height:6px;border-radius:50%;background:var(--accent3);animation:blink 1.2s infinite;}
    @keyframes blink{0%,100%{opacity:1;}50%{opacity:.2;}}

    main{max-width:1100px;margin:0 auto;padding:32px;}

    /* ── LIVE FEED ── */
    .section-label{font-family:var(--mono);font-size:10px;letter-spacing:4px;text-transform:uppercase;color:var(--muted);margin-bottom:16px;display:flex;align-items:center;gap:12px;}
    .section-label::after{content:'';flex:1;height:1px;background:var(--border);}

    #live-feed{margin-bottom:40px;min-height:80px;}

    .card{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--accent);margin-bottom:16px;overflow:hidden;animation:slideIn .3s ease;}
    .card.new{border-left-color:var(--accent3);animation:flashIn .4s ease;}
    @keyframes slideIn{from{opacity:0;transform:translateY(-8px);}to{opacity:1;transform:none;}}
    @keyframes flashIn{0%{background:rgba(127,255,107,.08);}100%{background:var(--surface);}}

    .card-header{padding:14px 20px;display:flex;align-items:flex-start;justify-content:space-between;gap:16px;cursor:pointer;user-select:none;}
    .card-header:hover{background:rgba(255,255,255,.02);}
    .card-title-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
    .card-label{font-size:15px;font-weight:700;color:var(--accent);letter-spacing:.5px;}
    .card-source{font-family:var(--mono);font-size:10px;color:var(--muted);border:1px solid var(--border);padding:2px 8px;letter-spacing:1px;text-transform:uppercase;}
    .card-originator{font-family:var(--mono);font-size:11px;color:var(--muted);}
    .card-meta{text-align:right;flex-shrink:0;}
    .card-time{font-family:var(--mono);font-size:10px;color:var(--muted);}
    .card-toggle{font-family:var(--mono);font-size:10px;color:var(--accent);margin-top:4px;letter-spacing:1px;}

    .card-body{padding:0 20px 20px;display:none;}
    .card-body.open{display:block;}

    .card-description{font-size:13px;color:var(--text);line-height:1.5;margin-bottom:16px;padding:10px 14px;background:var(--surface2);border-left:2px solid var(--border);}

    .chat-msg{font-family:var(--mono);font-size:12px;color:var(--accent2);background:rgba(255,107,53,.06);border:1px solid rgba(255,107,53,.2);padding:8px 14px;margin-bottom:16px;line-height:1.5;}

    .tags{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px;}
    .tag{font-family:var(--mono);font-size:10px;padding:3px 10px;border:1px solid var(--border);color:var(--muted);letter-spacing:1px;text-transform:uppercase;}
    .tag.entity{border-color:rgba(0,229,255,.3);color:var(--accent);}
    .tag.battle{border-color:rgba(255,107,53,.3);color:var(--accent2);}

    .effects{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-bottom:4px;}
    .effect{background:var(--surface2);border:1px solid var(--border);padding:14px;}
    .effect.recommended{border-color:rgba(0,229,255,.4);}
    .effect-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;}
    .effect-rank{font-family:var(--mono);font-size:10px;color:var(--muted);letter-spacing:1px;}
    .effect-verb{font-size:16px;font-weight:700;color:var(--accent);letter-spacing:1px;}
    .effect-verb.recommended{color:var(--accent3);}
    .effect-rec{font-family:var(--mono);font-size:9px;color:var(--accent3);border:1px solid var(--accent3);padding:2px 6px;letter-spacing:1px;}
    .effect-field{margin-bottom:8px;}
    .effect-field-label{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:3px;}
    .effect-field-val{font-size:12px;color:var(--text);line-height:1.4;}
    .ops-box{background:var(--bg);border:1px solid var(--border);padding:8px 10px;margin-top:6px;}
    .ops-label{font-family:var(--mono);font-size:9px;color:var(--muted);letter-spacing:2px;text-transform:uppercase;margin-bottom:4px;}
    .ops-val{font-size:11px;color:var(--text);}

    /* ── HISTORY ── */
    #history .card{border-left-color:var(--border);}
    #history .card:hover{border-left-color:var(--accent);}

    .empty{font-family:var(--mono);font-size:12px;color:var(--muted);padding:32px;text-align:center;border:1px dashed var(--border);}
  </style>
</head>
<body>
<header>
  <div class="logo">
    <div class="logo-badge">PAE</div>
    <div><div class="logo-text">Dashboard</div><div class="logo-sub">Pre-emptive Action Engine</div></div>
  </div>
  <nav>
    <a href="/">Config</a>
    <a href="/dashboard" class="active">Dashboard</a>
  </nav>
  <div class="live-badge"><div class="dot"></div><span id="live-status">CONNECTING...</span></div>
</header>

<main>
  <div class="section-label">Live Feed</div>
  <div id="live-feed"><div class="empty" id="live-empty">Waiting for assessments...</div></div>

  <div class="section-label">History</div>
  <div id="history"><div class="empty" id="hist-empty">No assessments yet.</div></div>
</main>

<script>
  const liveEl   = document.getElementById('live-feed');
  const histEl   = document.getElementById('history');
  const liveEmpty = document.getElementById('live-empty');
  const histEmpty = document.getElementById('hist-empty');
  const statusEl = document.getElementById('live-status');
  const MAX_LIVE = 3;
  let liveCards  = [];

  // ── Helpers ───────────────────────────────────────────────────────────

  function fmt(s){ return s ? String(s) : '—'; }

  function timeStr(iso){
    if(!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
  }

  function sourceLabel(r){
    if(r._source) return r._source.toUpperCase();
    return r.originator === 'SSE' ? 'SSE' : 'IRC';
  }

  // ── Card builder ──────────────────────────────────────────────────────

  function buildCard(r, isNew){
    const card = document.createElement('div');
    card.className = 'card' + (isNew ? ' new' : '');

    const effects = r.battleEffects || [];
    const entities = r.entitiesOfInterest || [];
    const battleEntities = r.battleEntity || [];
    const chat = r.chat || [];

    // Header
    const hdr = document.createElement('div');
    hdr.className = 'card-header';
    hdr.innerHTML = `
      <div>
        <div class="card-title-row">
          <span class="card-label">${esc(r.label || 'Untitled')}</span>
          <span class="card-source">${sourceLabel(r)}</span>
          <span class="card-originator">${esc(r.originator || '?')}</span>
        </div>
        <div style="margin-top:6px;font-family:var(--mono);font-size:11px;color:var(--muted)">
          ${effects.map(e=>`<span style="margin-right:12px;color:${e.recommended?'var(--accent3)':'var(--muted)'}">${esc(e.effectOperator)}</span>`).join('')}
        </div>
      </div>
      <div class="card-meta">
        <div class="card-time">${timeStr(r._receivedAt || r.lastUpdated)}</div>
        <div class="card-toggle">▼ EXPAND</div>
      </div>`;
    card.appendChild(hdr);

    // Body
    const body = document.createElement('div');
    body.className = 'card-body';

    // Chat message
    if(chat[0]) body.innerHTML += `<div class="chat-msg">📨 ${esc(chat[0])}</div>`;

    // Description
    if(r.description) body.innerHTML += `<div class="card-description">${esc(r.description)}</div>`;

    // Tags
    if(entities.length || battleEntities.length){
      const tags = document.createElement('div');
      tags.className = 'tags';
      entities.forEach(e=>{ const t=document.createElement('span');t.className='tag entity';t.textContent=e;tags.appendChild(t); });
      battleEntities.forEach(e=>{ const t=document.createElement('span');t.className='tag battle';t.textContent=e;tags.appendChild(t); });
      body.appendChild(tags);
    }

    // Effects
    if(effects.length){
      const grid = document.createElement('div');
      grid.className = 'effects';
      effects.forEach(ef=>{
        const ops = (ef.opsLimits||[])[0]||{};
        const div = document.createElement('div');
        div.className = 'effect' + (ef.recommended?' recommended':'');
        div.innerHTML = `
          <div class="effect-header">
            <span class="effect-rank">E0${ef.ranking||'?'}</span>
            ${ef.recommended?'<span class="effect-rec">RECOMMENDED</span>':''}
          </div>
          <div class="effect-verb ${ef.recommended?'recommended':''}">${esc(ef.effectOperator)}</div>
          ${ef.description?`<div class="effect-field" style="margin-top:10px"><div class="effect-field-label">Justification</div><div class="effect-field-val">${esc(ef.description)}</div></div>`:''}
          ${ef.timeWindow?`<div class="effect-field"><div class="effect-field-label">Time Window</div><div class="effect-field-val">${esc(ef.timeWindow)}</div></div>`:''}
          ${ef.stateHypothesis?`<div class="effect-field"><div class="effect-field-label">State Hypothesis</div><div class="effect-field-val">${esc(ef.stateHypothesis)}</div></div>`:''}
          ${ops.description?`<div class="ops-box"><div class="ops-label">Ops Limit</div><div class="ops-val">${esc(ops.description)}</div>${ops.battleEntity?`<div class="ops-val" style="margin-top:4px;color:var(--accent2)">${esc(ops.battleEntity)}</div>`:''}</div>`:''}`;
        grid.appendChild(div);
      });
      body.appendChild(grid);
    }

    card.appendChild(body);

    // Toggle
    hdr.addEventListener('click', ()=>{
      const open = body.classList.toggle('open');
      hdr.querySelector('.card-toggle').textContent = open ? '▲ COLLAPSE' : '▼ EXPAND';
    });

    return card;
  }

  function esc(s){
    return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // ── Add to live feed ──────────────────────────────────────────────────

  function addToLive(r){
    liveEmpty.style.display = 'none';
    const card = buildCard(r, true);
    // Auto-expand the latest card
    card.querySelector('.card-body').classList.add('open');
    card.querySelector('.card-toggle').textContent = '▲ COLLAPSE';
    liveEl.insertBefore(card, liveEl.firstChild);
    liveCards.unshift(card);
    // Keep only MAX_LIVE cards in the live section
    if(liveCards.length > MAX_LIVE){
      const old = liveCards.pop();
      old.remove();
    }
  }

  // ── Add to history ────────────────────────────────────────────────────

  function addToHistory(r){
    histEmpty.style.display = 'none';
    const card = buildCard(r, false);
    histEl.insertBefore(card, histEl.firstChild);
  }

  // ── Load history on page load ─────────────────────────────────────────

  async function loadHistory(){
    try{
      const res = await fetch('/assessments');
      const data = await res.json();
      if(data.length){
        histEmpty.style.display = 'none';
        data.forEach(r => addToHistory(r));
      }
    }catch(e){}
  }

  // ── SSE connection ────────────────────────────────────────────────────

  function connectSSE(){
    const es = new EventSource('/assessments/sse');

    es.onopen = () => {
      statusEl.textContent = 'LIVE';
      statusEl.style.color = 'var(--accent3)';
    };

    es.onmessage = (e) => {
      if(!e.data || e.data.trim() === '') return;
      try{
        const r = JSON.parse(e.data);
        addToLive(r);
        addToHistory(r);
      }catch(err){}
    };

    es.onerror = () => {
      statusEl.textContent = 'RECONNECTING...';
      statusEl.style.color = 'var(--accent2)';
      es.close();
      setTimeout(connectSSE, 3000);
    };
  }

  loadHistory();
  connectSSE();
</script>
</body>
</html>"""
