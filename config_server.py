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
    GET  /json             — raw JSON viewer tab
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
# ASSESSMENT STORE
# ---------------------------------------------------------------------------

_assessments: deque = deque(maxlen=200)
_sse_subscribers: list[asyncio.Queue] = []

# ---------------------------------------------------------------------------
# CLASSIFY STORE
# ---------------------------------------------------------------------------

_classify_logs: deque = deque(maxlen=500)
_classify_subscribers: list[asyncio.Queue] = []


def _broadcast_classify(record: dict) -> None:
    payload = f"data: {json.dumps(record)}\n\n"
    dead = []
    for q in _classify_subscribers:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _classify_subscribers.remove(q)


def _broadcast(record: dict) -> None:
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
# AI_ENDPOINT is the single URL field — pae_config.py detects lmstudio vs
# nanogpt from the URL automatically (nano-gpt.com = nanogpt, else lmstudio)
# ---------------------------------------------------------------------------

EDITABLE_FIELDS = {
    "GBC_API_URL": {
        "label":       "GBC API URL",
        "description": "Endpoint to push mapped assessments to — e.g. http://10.5.185.29:3016/paeoutputs",
        "placeholder": "http://10.5.185.29:3016/paeoutputs",
        "type":        "url",
    },
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
    "CLASSIFY_API_URL": {
        "label":       "Classify API URL",
        "description": "Message enrichment endpoint — adds callsigns and entities to AI context",
        "placeholder": "http://10.5.185.30:3060/classify",
        "type":        "url",
    },
    "CLASSIFY_TIMEOUT": {
        "label":       "Classify Timeout (seconds)",
        "description": "Max time to wait for classify response — keep short (3-5s)",
        "placeholder": "5",
        "type":        "number",
    },
    "TRIAGE_ENDPOINT": {
        "label":       "Triage Endpoint URL",
        "description": "AI endpoint for triage calls — leave blank to use the same as AI Endpoint",
        "placeholder": "https://nano-gpt.com/api/v1/chat/completions",
        "type":        "url",
    },
    "TRIAGE_MODEL": {
        "label":       "Triage Model",
        "description": "Model for triage — use a fast cheap model e.g. gpt-4o-mini",
        "placeholder": "gpt-4o-mini",
        "type":        "text",
    },
    "TRIAGE_TIMEOUT": {
        "label":       "Triage Timeout (seconds)",
        "description": "Max time to wait for triage response — keep short (5-10s)",
        "placeholder": "10",
        "type":        "number",
    },
    "AI_ENDPOINT": {
        "label":       "AI Endpoint URL",
        "description": "Set to LM Studio URL or NanoGPT URL — provider is detected automatically",
        "placeholder": "http://10.5.185.55:4334/v1/chat/completions",
        "type":        "url",
    },
    "AI_MODEL": {
        "label":       "AI Model",
        "description": "Model identifier — e.g. google/gemma-4-e4b for LM Studio or gpt-4o for NanoGPT",
        "placeholder": "google/gemma-4-e4b",
        "type":        "text",
    },
    "AI_API_KEY": {
        "label":       "AI API Key",
        "description": "API key — leave blank for LM Studio, required for NanoGPT",
        "placeholder": "sk-nano-... (leave blank for LM Studio)",
        "type":        "password",
    },
    "IRC_NICKNAME": {
        "label":       "IRC Bot Nickname",
        "description": "Name the bot uses on IRC — leave blank for a random name",
        "placeholder": "PAE_Bot",
        "type":        "text",
    },
    "IRC_SERVER": {
        "label":       "IRC Server",
        "description": "IRC server hostname or IP",
        "placeholder": "10.5.185.72",
        "type":        "text",
    },
    "IRC_CHANNEL": {
        "label":       "IRC Channels",
        "description": "Channels to listen on — separate multiple with commas e.g. #app_dev,#ops,#intel",
        "placeholder": "#app_dev,#ops",
        "type":        "text",
    },
    "SSE_RETRY_DELAY": {
        "label":       "SSE Retry Delay (seconds)",
        "description": "How long to wait before reconnecting to the orchestrator SSE stream",
        "placeholder": "5",
        "type":        "number",
    },
    # ── Database — configure when your DB is ready ────────────────────────
    "DB_HOST": {
        "label":       "Database Host",
        "description": "Hostname or IP of your PostgreSQL database server",
        "placeholder": "10.5.185.53",
        "type":        "text",
        "section":     "database",
    },
    "DB_PORT": {
        "label":       "Database Port",
        "description": "PostgreSQL port (default 5432)",
        "placeholder": "5432",
        "type":        "number",
        "section":     "database",
    },
    "DB_NAME": {
        "label":       "Database Name",
        "description": "Name of the PostgreSQL database",
        "placeholder": "shooca_db",
        "type":        "text",
        "section":     "database",
    },
    "DB_USER": {
        "label":       "Database User",
        "description": "PostgreSQL username",
        "placeholder": "shooca",
        "type":        "text",
        "section":     "database",
    },
    "DB_PASSWORD": {
        "label":       "Database Password",
        "description": "PostgreSQL password",
        "placeholder": "your-db-password",
        "type":        "password",
        "section":     "database",
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


def detect_provider(url: str) -> str:
    """Detect provider from URL — nano-gpt.com = nanogpt, anything else = lmstudio."""
    return "nanogpt" if "nano-gpt.com" in url else "lmstudio"


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


@app.get("/status")
def get_status():
    current = read_env()
    endpoint = current.get("AI_ENDPOINT", "")
    provider = detect_provider(endpoint) if endpoint else "lmstudio"
    db_host = current.get("DB_HOST", "")
    db_name = current.get("DB_NAME", "")
    db_status = f"{db_host}/{db_name}" if db_host and db_name else "NOT CONFIGURED"
    return {
        "orchestrator": current.get("ORCHESTRATOR_BASE_URL", "NOT SET"),
        "ai_endpoint":  endpoint or "NOT SET",
        "ai_provider":  provider.upper(),
        "ai_model":     current.get("AI_MODEL", "NOT SET"),
        "irc_server":   current.get("IRC_SERVER", "NOT SET"),
        "irc_channel":  current.get("IRC_CHANNEL", "NOT SET"),
        "db_status":    db_status,
    }

# ---------------------------------------------------------------------------
# ROUTES — assessments
# ---------------------------------------------------------------------------

@app.post("/assessment")
async def receive_assessment(request: Request):
    body = await request.json()
    record = body[0] if isinstance(body, list) else body
    record["_receivedAt"] = datetime.utcnow().isoformat() + "Z"
    _assessments.appendleft(record)
    _broadcast(record)
    return {"status": "received"}


@app.get("/assessments")
def get_assessments():
    return JSONResponse(content=list(_assessments))


@app.post("/classify-log")
async def receive_classify(request: Request):
    """main.py POSTs each classify API response here for the classify tab."""
    body = await request.json()
    body["_receivedAt"] = datetime.utcnow().isoformat() + "Z"
    _classify_logs.appendleft(body)
    _broadcast_classify(body)
    return {"status": "received"}


@app.get("/classify-logs")
def get_classify_logs():
    return JSONResponse(content=list(_classify_logs))


@app.get("/classify-logs/sse")
async def classify_sse(request: Request):
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _classify_subscribers.append(queue)

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
            if queue in _classify_subscribers:
                _classify_subscribers.remove(queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/assessments/sse")
async def assessments_sse(request: Request):
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


@app.get("/json", response_class=HTMLResponse)
def serve_json_viewer():
    return HTMLResponse(content=JSON_VIEWER_HTML)


@app.get("/classify", response_class=HTMLResponse)
def serve_classify_tab():
    return HTMLResponse(content=CLASSIFY_TAB_HTML)

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
    main{max-width:860px;margin:0 auto;padding:48px 40px;}
    .status-panel{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--accent);padding:20px 24px;margin-bottom:40px;display:grid;grid-template-columns:1fr 1fr;gap:12px 32px;}
    .status-item label{font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);font-family:var(--mono);}
    .status-item .val{font-family:var(--mono);font-size:12px;color:var(--accent);margin-top:4px;word-break:break-all;}
    .status-item .val.provider-nano{color:var(--accent2);}
    .section-title{font-size:10px;letter-spacing:4px;text-transform:uppercase;color:var(--muted);font-family:var(--mono);margin-bottom:24px;display:flex;align-items:center;gap:12px;}
    .section-title::after{content:'';flex:1;height:1px;background:var(--border);}
    .fields{display:flex;flex-direction:column;gap:20px;margin-bottom:36px;}
    .field{display:grid;grid-template-columns:220px 1fr;gap:0 24px;align-items:start;padding:20px 24px;background:var(--surface);border:1px solid var(--border);transition:border-color .2s;}
    .field:hover{border-color:rgba(0,229,255,.3);}
    .field.ai-field{border-left:3px solid var(--accent);}
    .field-meta label{font-size:12px;font-weight:600;color:var(--text);display:block;margin-bottom:6px;}
    .field-meta .desc{font-size:11px;color:var(--muted);line-height:1.5;}
    .field-input-wrap{position:relative;}
    .field input{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);font-family:var(--mono);font-size:12px;padding:10px 14px;outline:none;transition:.2s;}
    .field input:focus{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent);}
    .field input.modified{border-color:var(--accent2);box-shadow:0 0 0 1px var(--accent2);}
    .modified-tag{position:absolute;right:10px;top:50%;transform:translateY(-50%);font-size:9px;letter-spacing:2px;color:var(--accent2);font-family:var(--mono);text-transform:uppercase;pointer-events:none;}
    .provider-hint{font-family:var(--mono);font-size:10px;margin-top:6px;padding:6px 10px;border:1px solid var(--border);}
    .provider-hint.lm{color:var(--accent);border-color:rgba(0,229,255,.3);background:rgba(0,229,255,.04);}
    .provider-hint.nano{color:var(--accent2);border-color:rgba(255,107,53,.3);background:rgba(255,107,53,.04);}
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
    .field.db-field{border-left:3px solid #a855f7;}
    .db-section-title{font-size:10px;letter-spacing:4px;text-transform:uppercase;color:#a855f7;font-family:var(--mono);margin-bottom:24px;margin-top:8px;display:flex;align-items:center;gap:12px;}
    .db-section-title::after{content:'';flex:1;height:1px;background:rgba(168,85,247,.3);}
    .db-not-configured{font-family:var(--mono);font-size:10px;color:#a855f7;background:rgba(168,85,247,.06);border:1px solid rgba(168,85,247,.2);border-left:3px solid #a855f7;padding:12px 16px;margin-bottom:24px;line-height:1.6;}
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
    <a href="/json">JSON</a>
    <a href="/classify">Classify</a>
  </nav>
</header>
<main>
  <div class="status-panel">
    <div class="status-item"><label>Orchestrator</label><div class="val" id="st-orchestrator">loading...</div></div>
    <div class="status-item"><label>AI Provider</label><div class="val" id="st-provider">loading...</div></div>
    <div class="status-item"><label>IRC Server</label><div class="val" id="st-irc">loading...</div></div>
    <div class="status-item"><label>Active Model</label><div class="val" id="st-model">loading...</div></div>
    <div class="status-item"><label>Database</label><div class="val" id="st-db">loading...</div></div>
  </div>
  <div class="warning-box">⚠ Changes are written to .env immediately and take effect on the next message. To switch between LM Studio and NanoGPT, update the AI Endpoint URL field.</div>
  <div class="section-title">Configuration Fields</div>
  <div class="fields" id="fields"></div>
  <div class="actions">
    <button class="btn-save" id="btn-save" onclick="saveChanges()">Save Changes</button>
    <button class="btn-reset" onclick="resetForm()">Reset</button>
  </div>
</main>
<div class="toast" id="toast"></div>
<script>
  const AI_FIELDS = ['AI_ENDPOINT', 'AI_MODEL', 'AI_API_KEY'];
  let originalValues={},fieldMeta={};

  function detectProvider(url){
    return url && url.includes('nano-gpt.com') ? 'nanogpt' : 'lmstudio';
  }

  async function loadEnv(){
    const res=await fetch('/env');
    const data=await res.json();
    fieldMeta=data;originalValues={};
    const container=document.getElementById('fields');container.innerHTML='';
    const DB_FIELDS=['DB_HOST','DB_PORT','DB_NAME','DB_USER','DB_PASSWORD'];
    let dbSectionAdded=false;
    for(const[key,meta]of Object.entries(data)){
      originalValues[key]=meta.value;
      const t=meta.type==='password'?'password':'text';
      const isAI=AI_FIELDS.includes(key);
      const isDB=DB_FIELDS.includes(key);
      // Insert DB section title before first DB field
      if(isDB && !dbSectionAdded){
        const notice=document.createElement('div');
        notice.className='db-not-configured';
        notice.textContent='🗄  Database — configure when your DB is ready. These settings are used by db_writer.py to INSERT assessments directly into PostgreSQL.';
        container.appendChild(notice);
        const title=document.createElement('div');
        title.className='db-section-title';
        title.innerHTML='Database Connection';
        container.appendChild(title);
        dbSectionAdded=true;
      }
      const f=document.createElement('div');
      f.className='field'+(isAI?' ai-field':isDB?' db-field':'');
      f.innerHTML=`<div class="field-meta"><label>${meta.label}</label><div class="desc">${meta.description}</div></div><div class="field-input-wrap"><input type="${t}" id="field-${key}" data-key="${key}" value="${esc(meta.value)}" placeholder="${esc(meta.placeholder)}" oninput="onInput(this)" autocomplete="off"/><span class="modified-tag" id="tag-${key}" style="display:none">MODIFIED</span>${key==='AI_ENDPOINT'?'<div class="provider-hint lm" id="provider-hint">⚡ LM STUDIO detected</div>':''}</div>`;
      container.appendChild(f);
    }
    // Set initial provider hint
    const epEl=document.getElementById('field-AI_ENDPOINT');
    if(epEl) updateProviderHint(epEl.value);
    // Wire endpoint input to update hint live
    const epInput=document.getElementById('field-AI_ENDPOINT');
    if(epInput) epInput.addEventListener('input', e=>updateProviderHint(e.target.value));
  }

  function updateProviderHint(url){
    const hint=document.getElementById('provider-hint');
    if(!hint)return;
    const p=detectProvider(url);
    if(p==='nanogpt'){
      hint.className='provider-hint nano';
      hint.textContent='☁ NANOGPT detected — make sure AI API Key is set';
    } else {
      hint.className='provider-hint lm';
      hint.textContent='⚡ LM STUDIO detected — AI API Key not required';
    }
  }

  async function loadStatus(){
    try{
      const res=await fetch('/status');const d=await res.json();
      document.getElementById('st-orchestrator').textContent=d.orchestrator;
      document.getElementById('st-irc').textContent=d.irc_server+' '+d.irc_channel;
      document.getElementById('st-model').textContent=d.ai_model;
      document.getElementById('st-db').textContent=d.db_status;
      const provEl=document.getElementById('st-provider');
      provEl.textContent=d.ai_provider;
      provEl.className='val'+(d.ai_provider==='NANOGPT'?' provider-nano':'');
    }catch(e){}
  }

  function onInput(el){
    const key=el.dataset.key,tag=document.getElementById('tag-'+key);
    if(el.value!==originalValues[key]){el.classList.add('modified');tag.style.display='block';}
    else{el.classList.remove('modified');tag.style.display='none';}
  }

  function resetForm(){
    for(const key of Object.keys(originalValues)){
      const el=document.getElementById('field-'+key);
      if(el){
        el.value=originalValues[key];
        el.classList.remove('modified');
        document.getElementById('tag-'+key).style.display='none';
        if(key==='AI_ENDPOINT') updateProviderHint(el.value);
      }
    }
  }

  async function saveChanges(){
    const values={};let hasChanges=false;
    for(const key of Object.keys(originalValues)){
      const el=document.getElementById('field-'+key);
      if(el&&el.value!==originalValues[key]){values[key]=el.value;hasChanges=true;}
    }
    if(!hasChanges){showToast('No changes to save.',false);return;}
    const btn=document.getElementById('btn-save');btn.disabled=true;btn.textContent='Saving...';
    try{
      const res=await fetch('/env',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({values})});
      if(res.ok){const d=await res.json();showToast('Saved: '+d.updated.join(', '),true);await loadEnv();await loadStatus();}
      else showToast('Save failed.',false);
    }catch(e){showToast('Network error.',false);}
    btn.disabled=false;btn.textContent='Save Changes';
  }

  function showToast(msg,ok){
    const t=document.getElementById('toast');
    t.textContent=(ok?'✓  ':'✗  ')+msg;
    t.className='toast show '+(ok?'success':'error');
    setTimeout(()=>{t.className='toast';},3500);
  }

  function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

  loadEnv();loadStatus();setInterval(loadStatus,10000);
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
    <a href="/json">JSON</a>
    <a href="/classify">Classify</a>
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
  const liveEl=document.getElementById('live-feed');
  const histEl=document.getElementById('history');
  const liveEmpty=document.getElementById('live-empty');
  const histEmpty=document.getElementById('hist-empty');
  const statusEl=document.getElementById('live-status');
  const MAX_LIVE=3;
  let liveCards=[];

  function timeStr(iso){if(!iso)return '—';const d=new Date(iso);return d.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'});}
  function sourceLabel(r){if(r._source)return r._source.toUpperCase();return r.originator==='SSE'?'SSE':'IRC';}

  function buildCard(r,isNew){
    const card=document.createElement('div');
    card.className='card'+(isNew?' new':'');
    const effects=r.battleEffects||[];
    const entities=r.entitiesOfInterest||[];
    const battleEntities=r.battleEntity||[];
    const chat=r.chat||[];
    const hdr=document.createElement('div');
    hdr.className='card-header';
    hdr.innerHTML=`
      <div>
        <div class="card-title-row">
          <span class="card-label">${esc(r.label||'Untitled')}</span>
          <span class="card-source">${sourceLabel(r)}</span>
          <span class="card-originator">${esc(r.originator||'?')}</span>
        </div>
        <div style="margin-top:6px;font-family:var(--mono);font-size:11px;color:var(--muted)">
          ${effects.map(e=>`<span style="margin-right:12px;color:${e.recommended?'var(--accent3)':'var(--muted)'}">${esc(e.effectOperator)}</span>`).join('')}
        </div>
      </div>
      <div class="card-meta">
        <div class="card-time">${timeStr(r._receivedAt||r.lastUpdated)}</div>
        <div class="card-toggle">▼ EXPAND</div>
      </div>`;
    card.appendChild(hdr);
    const body=document.createElement('div');
    body.className='card-body';
    if(chat[0])body.innerHTML+=`<div class="chat-msg">📨 ${esc(chat[0])}</div>`;
    if(r.description)body.innerHTML+=`<div class="card-description">${esc(r.description)}</div>`;
    if(entities.length||battleEntities.length){
      const tags=document.createElement('div');tags.className='tags';
      entities.forEach(e=>{const t=document.createElement('span');t.className='tag entity';t.textContent=e;tags.appendChild(t);});
      battleEntities.forEach(e=>{const t=document.createElement('span');t.className='tag battle';t.textContent=e;tags.appendChild(t);});
      body.appendChild(tags);
    }
    if(effects.length){
      const grid=document.createElement('div');grid.className='effects';
      effects.forEach(ef=>{
        const ops=(ef.opsLimits||[])[0]||{};
        const div=document.createElement('div');
        div.className='effect'+(ef.recommended?' recommended':'');
        div.innerHTML=`
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
    hdr.addEventListener('click',()=>{
      const open=body.classList.toggle('open');
      hdr.querySelector('.card-toggle').textContent=open?'▲ COLLAPSE':'▼ EXPAND';
    });
    return card;
  }

  function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

  function addToLive(r){
    liveEmpty.style.display='none';
    const card=buildCard(r,true);
    card.querySelector('.card-body').classList.add('open');
    card.querySelector('.card-toggle').textContent='▲ COLLAPSE';
    liveEl.insertBefore(card,liveEl.firstChild);
    liveCards.unshift(card);
    if(liveCards.length>MAX_LIVE){const old=liveCards.pop();old.remove();}
  }

  function addToHistory(r){
    histEmpty.style.display='none';
    const card=buildCard(r,false);
    histEl.insertBefore(card,histEl.firstChild);
  }

  async function loadHistory(){
    try{
      const res=await fetch('/assessments');
      const data=await res.json();
      if(data.length){histEmpty.style.display='none';data.forEach(r=>addToHistory(r));}
    }catch(e){}
  }

  function connectSSE(){
    const es=new EventSource('/assessments/sse');
    es.onopen=()=>{statusEl.textContent='LIVE';statusEl.style.color='var(--accent3)';};
    es.onmessage=(e)=>{
      if(!e.data||e.data.trim()==='')return;
      try{const r=JSON.parse(e.data);addToLive(r);addToHistory(r);}catch(err){}
    };
    es.onerror=()=>{
      statusEl.textContent='RECONNECTING...';statusEl.style.color='var(--accent2)';
      es.close();setTimeout(connectSSE,3000);
    };
  }

  loadHistory();connectSSE();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# JSON VIEWER HTML
# ---------------------------------------------------------------------------

JSON_VIEWER_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PAE JSON Viewer</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
    :root{
      --bg:#060a0f;--surface:#0b1219;--surface2:#0f1a24;--border:#162030;
      --accent:#00e5ff;--accent2:#ff6b35;--accent3:#7fff6b;--accent4:#a855f7;
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

    main{max-width:1200px;margin:0 auto;padding:32px;}

    .toolbar{display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap;}
    .section-label{font-family:var(--mono);font-size:10px;letter-spacing:4px;text-transform:uppercase;color:var(--muted);display:flex;align-items:center;gap:12px;flex:1;}
    .section-label::after{content:'';flex:1;height:1px;background:var(--border);}
    .btn{font-family:var(--mono);font-size:11px;letter-spacing:2px;text-transform:uppercase;padding:8px 18px;border:1px solid var(--border);background:transparent;color:var(--muted);cursor:pointer;transition:.2s;}
    .btn:hover{border-color:var(--accent);color:var(--accent);}
    .btn.active{border-color:var(--accent);color:var(--accent);background:rgba(0,229,255,.05);}
    .btn-copy{border-color:var(--accent4);color:var(--accent4);}
    .btn-copy:hover{background:rgba(168,85,247,.08);}
    .btn-clear{border-color:var(--accent2);color:var(--accent2);}
    .btn-clear:hover{background:rgba(255,107,53,.08);}

    .record-list{display:flex;flex-direction:column;gap:12px;}

    .record{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--accent);overflow:hidden;}
    .record.new{border-left-color:var(--accent3);animation:flash .4s ease;}
    @keyframes flash{0%{background:rgba(127,255,107,.06);}100%{background:var(--surface);}}

    .record-header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;cursor:pointer;user-select:none;gap:12px;}
    .record-header:hover{background:rgba(255,255,255,.02);}
    .record-meta{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
    .record-label{font-size:14px;font-weight:700;color:var(--accent);}
    .record-id{font-family:var(--mono);font-size:10px;color:var(--muted);}
    .record-time{font-family:var(--mono);font-size:10px;color:var(--muted);}
    .record-source{font-family:var(--mono);font-size:10px;color:var(--muted);border:1px solid var(--border);padding:2px 8px;text-transform:uppercase;}
    .record-actions{display:flex;gap:8px;align-items:center;flex-shrink:0;}
    .btn-sm{font-family:var(--mono);font-size:10px;letter-spacing:1px;padding:4px 12px;border:1px solid var(--border);background:transparent;color:var(--muted);cursor:pointer;transition:.2s;text-transform:uppercase;}
    .btn-sm:hover{border-color:var(--accent4);color:var(--accent4);}
    .toggle-arrow{font-family:var(--mono);font-size:11px;color:var(--accent);}

    .record-body{display:none;border-top:1px solid var(--border);}
    .record-body.open{display:block;}

    .json-block{
      background:var(--bg);
      padding:20px;
      overflow-x:auto;
      font-family:var(--mono);
      font-size:12px;
      line-height:1.7;
      white-space:pre;
      color:var(--text);
    }

    /* Syntax highlight colours */
    .j-key{color:var(--accent);}
    .j-str{color:var(--accent3);}
    .j-num{color:var(--accent2);}
    .j-bool{color:var(--accent4);}
    .j-null{color:var(--muted);}

    .empty{font-family:var(--mono);font-size:12px;color:var(--muted);padding:48px;text-align:center;border:1px dashed var(--border);}

    .toast{position:fixed;bottom:24px;right:24px;padding:12px 20px;font-family:var(--mono);font-size:11px;letter-spacing:1px;background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--accent3);color:var(--accent3);transform:translateY(20px);opacity:0;transition:.3s;z-index:999;}
    .toast.show{transform:translateY(0);opacity:1;}
  </style>
</head>
<body>
<header>
  <div class="logo">
    <div class="logo-badge">PAE</div>
    <div><div class="logo-text">JSON Viewer</div><div class="logo-sub">Pre-emptive Action Engine</div></div>
  </div>
  <nav>
    <a href="/">Config</a>
    <a href="/dashboard">Dashboard</a>
    <a href="/json" class="active">JSON</a>
    <a href="/classify">Classify</a>
  </nav>
  <div class="live-badge"><div class="dot"></div><span id="live-status">CONNECTING...</span></div>
</header>

<main>
  <div class="toolbar">
    <div class="section-label">Assessment Output</div>
    <button class="btn btn-copy" onclick="copyAll()">Copy Latest</button>
    <button class="btn btn-clear" onclick="clearAll()">Clear</button>
  </div>
  <div class="record-list" id="records">
    <div class="empty" id="empty-msg">Waiting for assessments...</div>
  </div>
</main>

<div class="toast" id="toast"></div>

<script>
  const recordsEl = document.getElementById('records');
  const emptyEl   = document.getElementById('empty-msg');
  const statusEl  = document.getElementById('live-status');
  let allRecords  = [];

  // ── Syntax highlighter ────────────────────────────────────────────────
  function highlight(json) {
    return json
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/("(\\.|[^"\\])*") *:/g, '<span class="j-key">$1</span>:')
      .replace(/: *("(\\.|[^"\\])*")/g, ': <span class="j-str">$1</span>')
      .replace(/: *(-?[0-9]+\.?[0-9]*)/g, ': <span class="j-num">$1</span>')
      .replace(/: *(true|false)/g, ': <span class="j-bool">$1</span>')
      .replace(/: *(null)/g, ': <span class="j-null">$1</span>');
  }

  function timeStr(iso){
    if(!iso) return '';
    return new Date(iso).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  }

  // ── Build record element ──────────────────────────────────────────────
  function buildRecord(r, isNew) {
    const pretty  = JSON.stringify(r, null, 2);
    const id      = r.requestId || r.id || '?';
    const label   = r.label || 'Assessment';
    const source  = (r._source || (r.originator === 'SSE' ? 'SSE' : 'IRC')).toUpperCase();
    const time    = timeStr(r._receivedAt || r.lastUpdated);

    const wrap = document.createElement('div');
    wrap.className = 'record' + (isNew ? ' new' : '');
    wrap.dataset.json = pretty;

    wrap.innerHTML = `
      <div class="record-header" onclick="toggleRecord(this)">
        <div class="record-meta">
          <span class="record-label">${esc(label)}</span>
          <span class="record-source">${source}</span>
          <span class="record-id">${esc(id)}</span>
          <span class="record-time">${time}</span>
        </div>
        <div class="record-actions">
          <button class="btn-sm" onclick="copyRecord(event, this)">Copy</button>
          <span class="toggle-arrow">▼</span>
        </div>
      </div>
      <div class="record-body open">
        <div class="json-block">${highlight(pretty)}</div>
      </div>`;

    return wrap;
  }

  function toggleRecord(hdr) {
    const body  = hdr.nextElementSibling;
    const arrow = hdr.querySelector('.toggle-arrow');
    const open  = body.classList.toggle('open');
    arrow.textContent = open ? '▼' : '▶';
  }

  function copyRecord(e, btn) {
    e.stopPropagation();
    const json = btn.closest('.record').dataset.json;
    navigator.clipboard.writeText(json).then(() => showToast('Copied to clipboard'));
  }

  function copyAll() {
    if (!allRecords.length) { showToast('Nothing to copy'); return; }
    navigator.clipboard.writeText(JSON.stringify(allRecords[0], null, 2))
      .then(() => showToast('Latest JSON copied'));
  }

  function clearAll() {
    allRecords = [];
    recordsEl.innerHTML = '';
    recordsEl.appendChild(emptyEl);
    emptyEl.style.display = 'block';
  }

  function addRecord(r, isNew) {
    emptyEl.style.display = 'none';
    allRecords.unshift(r);
    const el = buildRecord(r, isNew);
    recordsEl.insertBefore(el, recordsEl.firstChild);
  }

  function esc(s) {
    return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = '✓  ' + msg;
    t.className = 'toast show';
    setTimeout(() => { t.className = 'toast'; }, 2500);
  }

  // ── Load history ──────────────────────────────────────────────────────
  async function loadHistory() {
    try {
      const res  = await fetch('/assessments');
      const data = await res.json();
      if (data.length) {
        data.forEach(r => addRecord(r, false));
        // Collapse all except the first on load
        const bodies = recordsEl.querySelectorAll('.record-body');
        bodies.forEach((b, i) => {
          if (i > 0) {
            b.classList.remove('open');
            b.previousElementSibling.querySelector('.toggle-arrow').textContent = '▶';
          }
        });
      }
    } catch(e) {}
  }

  // ── SSE connection ────────────────────────────────────────────────────
  function connectSSE() {
    const es = new EventSource('/assessments/sse');
    es.onopen = () => {
      statusEl.textContent = 'LIVE';
      statusEl.style.color = 'var(--accent3)';
    };
    es.onmessage = (e) => {
      if (!e.data || e.data.trim() === '') return;
      try { addRecord(JSON.parse(e.data), true); } catch(err) {}
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

# ---------------------------------------------------------------------------
# CLASSIFY TAB HTML
# ---------------------------------------------------------------------------

CLASSIFY_TAB_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PAE Classify</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
    :root{
      --bg:#060a0f;--surface:#0b1219;--surface2:#0f1a24;--border:#162030;
      --accent:#00e5ff;--accent2:#ff6b35;--accent3:#7fff6b;--accent4:#a855f7;
      --text:#b8ccd8;--muted:#3a5060;--mono:'Share Tech Mono',monospace;
      --sans:'Rajdhani',sans-serif;
      --high:#ff4466;--med:#ffaa00;--low:#4a6080;
    }
    *{box-sizing:border-box;margin:0;padding:0;}
    body{background:var(--bg);color:var(--text);font-family:var(--sans);min-height:100vh;}
    body::before{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,229,255,.008) 3px,rgba(0,229,255,.008) 4px);pointer-events:none;z-index:1000;}
    header{background:var(--surface);border-bottom:1px solid var(--border);padding:16px 32px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;}
    .logo{display:flex;align-items:center;gap:12px;}
    .logo-badge{width:34px;height:34px;border:2px solid var(--accent4);display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:12px;color:var(--accent4);}
    .logo-text{font-size:14px;font-weight:700;letter-spacing:4px;text-transform:uppercase;color:var(--accent4);}
    .logo-sub{font-size:10px;color:var(--muted);letter-spacing:2px;text-transform:uppercase;}
    nav{display:flex;gap:4px;}
    nav a{font-family:var(--mono);font-size:11px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);text-decoration:none;padding:8px 16px;border:1px solid transparent;transition:.2s;}
    nav a:hover{color:var(--accent);border-color:var(--border);}
    nav a.active{color:var(--accent4);border-color:var(--accent4);background:rgba(168,85,247,.05);}
    .live-badge{display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:11px;color:var(--accent3);}
    .dot{width:6px;height:6px;border-radius:50%;background:var(--accent3);animation:blink 1.2s infinite;}
    @keyframes blink{0%,100%{opacity:1;}50%{opacity:.2;}}

    main{max-width:1200px;margin:0 auto;padding:32px;}

    .toolbar{display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap;}
    .section-label{font-family:var(--mono);font-size:10px;letter-spacing:4px;text-transform:uppercase;color:var(--muted);display:flex;align-items:center;gap:12px;flex:1;}
    .section-label::after{content:'';flex:1;height:1px;background:var(--border);}
    .btn{font-family:var(--mono);font-size:11px;letter-spacing:2px;text-transform:uppercase;padding:8px 18px;border:1px solid var(--border);background:transparent;color:var(--muted);cursor:pointer;transition:.2s;}
    .btn:hover{border-color:var(--accent);color:var(--accent);}
    .btn-clear{border-color:var(--accent2);color:var(--accent2);}
    .btn-clear:hover{background:rgba(255,107,53,.08);}

    .feed{display:flex;flex-direction:column;gap:10px;}

    .card{background:var(--surface);border:1px solid var(--border);overflow:hidden;animation:slideIn .25s ease;}
    .card.new{animation:flashIn .4s ease;}
    @keyframes slideIn{from{opacity:0;transform:translateY(-6px);}to{opacity:1;transform:none;}}
    @keyframes flashIn{0%{background:rgba(168,85,247,.08);}100%{background:var(--surface);}}

    .card-header{padding:12px 16px;display:flex;align-items:center;gap:12px;cursor:pointer;user-select:none;flex-wrap:wrap;}
    .card-header:hover{background:rgba(255,255,255,.02);}

    /* Tier badge */
    .tier{font-family:var(--mono);font-size:10px;letter-spacing:1px;padding:3px 10px;border:1px solid;text-transform:uppercase;flex-shrink:0;}
    .tier.HIGH_VALUE{border-color:var(--high);color:var(--high);background:rgba(255,68,102,.06);}
    .tier.MEDIUM_VALUE{border-color:var(--med);color:var(--med);background:rgba(255,170,0,.06);}
    .tier.LOW_VALUE{border-color:var(--low);color:var(--low);}

    .card-msg{font-family:var(--mono);font-size:12px;color:var(--text);flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .card-sender{font-family:var(--mono);font-size:11px;color:var(--accent4);flex-shrink:0;}
    .card-channel{font-family:var(--mono);font-size:10px;color:var(--muted);flex-shrink:0;}
    .card-time{font-family:var(--mono);font-size:10px;color:var(--muted);flex-shrink:0;}
    .card-score{font-family:var(--mono);font-size:10px;color:var(--muted);flex-shrink:0;}
    .toggle{font-family:var(--mono);font-size:10px;color:var(--accent4);flex-shrink:0;}

    .card-body{display:none;border-top:1px solid var(--border);padding:16px;}
    .card-body.open{display:grid;grid-template-columns:1fr 1fr;gap:16px;}

    .section{background:var(--surface2);padding:12px 14px;}
    .section-head{font-family:var(--mono);font-size:9px;letter-spacing:3px;text-transform:uppercase;color:var(--muted);margin-bottom:8px;}
    .section.full{grid-column:1/-1;}

    .tag-row{display:flex;flex-wrap:wrap;gap:6px;}
    .tag{font-family:var(--mono);font-size:10px;padding:3px 10px;border:1px solid var(--border);color:var(--text);letter-spacing:.5px;}
    .tag.callsign{border-color:rgba(168,85,247,.4);color:var(--accent4);}
    .tag.entity{border-color:rgba(0,229,255,.3);color:var(--accent);}
    .tag.bin{border-color:rgba(127,255,107,.25);color:var(--accent3);}

    .meta-row{display:flex;justify-content:space-between;margin-bottom:6px;}
    .meta-key{font-family:var(--mono);font-size:10px;color:var(--muted);}
    .meta-val{font-family:var(--mono);font-size:10px;color:var(--text);}

    .reasoning-text{font-family:var(--mono);font-size:11px;color:var(--text);line-height:1.6;}

    .confidence-bar-wrap{height:4px;background:var(--border);margin-top:8px;border-radius:2px;}
    .confidence-bar{height:4px;border-radius:2px;background:var(--accent4);transition:width .4s;}

    .empty{font-family:var(--mono);font-size:12px;color:var(--muted);padding:48px;text-align:center;border:1px dashed var(--border);}

    .toast{position:fixed;bottom:24px;right:24px;padding:12px 20px;font-family:var(--mono);font-size:11px;background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--accent4);color:var(--accent4);transform:translateY(20px);opacity:0;transition:.3s;z-index:999;}
    .toast.show{transform:translateY(0);opacity:1;}
  </style>
</head>
<body>
<header>
  <div class="logo">
    <div class="logo-badge">CLS</div>
    <div><div class="logo-text">Classify Feed</div><div class="logo-sub">Pre-emptive Action Engine</div></div>
  </div>
  <nav>
    <a href="/">Config</a>
    <a href="/dashboard">Dashboard</a>
    <a href="/json">JSON</a>
    <a href="/classify" class="active">Classify</a>
  </nav>
  <div class="live-badge"><div class="dot"></div><span id="live-status">CONNECTING...</span></div>
</header>

<main>
  <div class="toolbar">
    <div class="section-label">Classify API Feed</div>
    <button class="btn btn-clear" onclick="clearAll()">Clear</button>
  </div>
  <div class="feed" id="feed">
    <div class="empty" id="empty-msg">Waiting for classify responses...</div>
  </div>
</main>

<div class="toast" id="toast"></div>

<script>
  const feedEl   = document.getElementById('feed');
  const emptyEl  = document.getElementById('empty-msg');
  const statusEl = document.getElementById('live-status');

  function esc(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function timeStr(iso){ if(!iso)return ''; return new Date(iso).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'}); }

  function tierClass(tier){
    if(!tier) return 'LOW_VALUE';
    if(tier.includes('HIGH')) return 'HIGH_VALUE';
    if(tier.includes('MED'))  return 'MEDIUM_VALUE';
    return 'LOW_VALUE';
  }

  function buildCard(r, isNew){
    const card = document.createElement('div');
    card.className = 'card' + (isNew ? ' new' : '');

    const tier      = r.importance_tier || 'UNKNOWN';
    const tc        = tierClass(tier);
    const msg       = r.raw_content || r.processed_content || '';
    const sender    = r.sender || '?';
    const channel   = r.channel || '';
    const time      = r.timestamp || timeStr(r._receivedAt);
    const score     = r.importance_score ?? '?';
    const conf      = r.confidence ?? 0;
    const confPct   = Math.round(conf * 100);
    const reasoning = r.reasoning || '';

    // Entities
    const entRef    = r.entities_referenced || {};
    const callsigns = entRef.callsigns || [];
    const tracks    = entRef.track_numbers || [];
    const coords    = entRef.coordinates || [];
    const missions  = entRef.mission_numbers || [];

    // Matched bins
    const mBins  = r.matched_bins || {};
    const bins   = r.bins || [];
    const allBinKeys = bins.map(b => b.bin_key);

    // All entity tags
    const entityTags = [...tracks, ...coords, ...missions];

    // Build callsign tags
    const csTags = callsigns.map(c =>
      `<span class="tag callsign">${esc(c)}</span>`
    ).join('');

    // Build entity tags
    const entTags = entityTags.map(e =>
      `<span class="tag entity">${esc(e)}</span>`
    ).join('');

    // Build bin tags
    const binTags = allBinKeys.slice(0, 8).map(b =>
      `<span class="tag bin">${esc(b)}</span>`
    ).join('');

    card.innerHTML = `
      <div class="card-header" onclick="toggle(this)">
        <span class="tier ${tc}">${esc(tier)}</span>
        <span class="card-msg">${esc(msg)}</span>
        <span class="card-sender">${esc(sender)}</span>
        <span class="card-channel">${esc(channel)}</span>
        <span class="card-time">${esc(time)}</span>
        <span class="card-score">score ${esc(String(score))}</span>
        <span class="toggle">▼</span>
      </div>
      <div class="card-body">
        <div class="section">
          <div class="section-head">Callsigns</div>
          <div class="tag-row">${csTags || '<span style="color:var(--muted);font-family:var(--mono);font-size:11px;">none identified</span>'}</div>
        </div>
        <div class="section">
          <div class="section-head">Entities</div>
          <div class="tag-row">${entTags || '<span style="color:var(--muted);font-family:var(--mono);font-size:11px;">none identified</span>'}</div>
        </div>
        <div class="section">
          <div class="section-head">Classification</div>
          <div class="meta-row"><span class="meta-key">Category</span><span class="meta-val">${esc(r.category||'')}</span></div>
          <div class="meta-row"><span class="meta-key">Lane</span><span class="meta-val">${esc(r.classification_lane||'')}</span></div>
          <div class="meta-row"><span class="meta-key">Path</span><span class="meta-val">${esc(r.classification_path||'')}</span></div>
          <div class="meta-row"><span class="meta-key">Confidence</span><span class="meta-val">${confPct}%</span></div>
          <div class="confidence-bar-wrap"><div class="confidence-bar" style="width:${confPct}%"></div></div>
        </div>
        <div class="section">
          <div class="section-head">Matched Bins</div>
          <div class="tag-row">${binTags || '<span style="color:var(--muted);font-family:var(--mono);font-size:11px;">none</span>'}</div>
        </div>
        <div class="section full">
          <div class="section-head">Classifier Reasoning</div>
          <div class="reasoning-text">${esc(reasoning) || '—'}</div>
        </div>
      </div>`;

    return card;
  }

  function toggle(hdr){
    const body  = hdr.nextElementSibling;
    const arrow = hdr.querySelector('.toggle');
    const open  = body.classList.toggle('open');
    arrow.textContent = open ? '▲' : '▼';
  }

  function addCard(r, isNew){
    emptyEl.style.display = 'none';
    const card = buildCard(r, isNew);
    if(isNew){
      // Auto-expand new cards
      card.querySelector('.card-body').classList.add('open');
      card.querySelector('.toggle').textContent = '▲';
    }
    feedEl.insertBefore(card, feedEl.firstChild);
  }

  function clearAll(){
    feedEl.innerHTML = '';
    feedEl.appendChild(emptyEl);
    emptyEl.style.display = 'block';
  }

  async function loadHistory(){
    try{
      const res  = await fetch('/classify-logs');
      const data = await res.json();
      if(data.length){
        emptyEl.style.display = 'none';
        data.forEach(r => addCard(r, false));
        // Collapse all on history load
        feedEl.querySelectorAll('.card-body').forEach(b => b.classList.remove('open'));
        feedEl.querySelectorAll('.toggle').forEach(t => t.textContent = '▼');
      }
    }catch(e){}
  }

  function connectSSE(){
    const es = new EventSource('/classify-logs/sse');
    es.onopen = () => {
      statusEl.textContent = 'LIVE';
      statusEl.style.color = 'var(--accent3)';
    };
    es.onmessage = (e) => {
      if(!e.data || e.data.trim() === '') return;
      try{ addCard(JSON.parse(e.data), true); }catch(err){}
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