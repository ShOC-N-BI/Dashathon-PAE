# PAE — Pre-emptive Action Engine

```
;;II::;II::;I::,;;;;::;;I,:;;I;;;;;:";;;:";;;;::;;;::;;;:,I;;:,;;::,;I
;:,;III,IlI;,;I:,,  PRE-EMPTIVE ACTION ENGINE  ;I;:,:,,,::;,,":;I"^,
;;II::;II::;I::,;;;;  ██████╗  █████╗ ███████╗  :;;,;;;,,:;:,":;,,
;;;:::I;:::;;;:::;;::  ██╔══██╗██╔══██╗██╔════╝  ;;::::;;;:;;;;;;:
;::;;:::;;::,:;;;::;;  ██████╔╝███████║█████╗    ;;::;;:;II;;:;;I::
:;:;;:::;;;:::;;,:;::  ██╔═══╝ ██╔══██║██╔══╝   ;;:;I;;:;;I::;I;;,
;Il;:;II;::;;:;,;;;I,  ██║     ██║  ██║███████╗  I;:II;;,;I;:,:;;
:;;;:::;::;:;::;;:::;  ╚═╝     ╚═╝  ╚═╝╚══════╝ ::;;;;;;;;;;;;;;
;;II::;II::;I::,;;;;::;;I,:;;I;;;;;:";;;:";;;;::;;;::;;;:,I;;:,;;::,;I
```

A tactical AI microservice that listens to J-chat messages from IRC and reassessment triggers from an orchestrator cluster via SSE. Every message is triaged by AI before being assessed. Relevant messages receive a full battle JSON assessment which is pushed to the GBC API, the orchestrator, and optionally a PostgreSQL database.

---

## How It Works — The Full Pipeline

Every message passes through a two-stage AI pipeline:

```
Input (IRC or SSE)
    │
    ▼
pipeline/triage.py       — Stage 1: AI decides if message is tactically relevant
    │ not relevant → discard (FILTERED — NOT TACTICAL)
    │ relevant ↓
    ▼
ai/agent.py              — Stage 2: Full AI battle assessment
    │
    ▼
output/log_writer.py     — always writes to tactical_output.log
output/db_writer.py      — inserts to PostgreSQL (if DB configured)
output/gbc_api_client.py — POSTs full battle JSON to GBC API (if configured)
config_server.py         — pushes to live dashboard
client/pae_output_client.py — POSTs to orchestrator /paeoutputs
```

There are two input paths:

**Path 1 — IRC** — the bot joins one or more J-chat channels and listens for messages in real time. Every message is triaged before reaching the full assessment.

**Path 2 — SSE** — the orchestrator pushes a `PaeInputCreated` event when another application in the cluster wants a message reassessed. The `trackId` field contains the message text. Both paths call the same `run_pipeline()` function.

---

## Project Structure

```
pae/
├── main.py                        # Entry point — wires all inputs and outputs
├── pae_config.py                  # All settings — reads .env at startup and on demand
├── config_server.py               # Web UI server (port 8080) — config + dashboard
├── .env                           # Your secrets — never commit this
├── .env.example                   # Template — copy to .env and fill in
├── Dockerfile                     # Single image used by all three Docker services
├── docker-compose.yml             # Runs pae + config + emulator
├── requirements.txt               # Python dependencies
│
├── ai/
│   └── agent.py                   # Full AI battle assessment engine
│
├── client/
│   ├── http_client.py             # Shared HTTP client for orchestrator requests
│   ├── pae_sse_client.py          # SSE listener — receives retrigger events
│   └── pae_output_client.py       # POSTs completed assessments to orchestrator
│
├── irc/
│   └── listener.py                # IRC bot — connects, joins channels, reads messages
│
├── pipeline/
│   ├── triage.py                  # Stage 1: AI relevance filter
│   ├── filter.py                  # Legacy character filter (kept for reference)
│   └── builder.py                 # Generates unique request IDs
│
├── output/
│   ├── log_writer.py              # Writes assessments to local log file
│   ├── db_writer.py               # Inserts assessments into PostgreSQL
│   ├── gbc_api_client.py          # POSTs full battle JSON to GBC API
│   └── api_push.py                # Generic API push (legacy)
│
├── schemas/
│   └── pae_schemas.py             # Pydantic models for orchestrator data contracts
│
├── data/
│   ├── standard_tactical_chat_abbreviations.csv
│   ├── brevity_codes_2025_standard.csv
│   └── tactical_glossary_abbreviations.csv
│
└── tests/
    └── emulator/
        ├── pae_combined_emulator.py   # Fake orchestrator for local testing
        └── pae_run_emulator.py        # Starts the emulator
```

---

## File-by-File Function Reference

### `main.py` — Entry Point

**`make_dashboard(last_msg, last_user, verbs, status, source) → Table`**
Builds the Rich terminal table showing live activity. Displays timestamp, source (IRC/SSE), raw message, three AI verbs, and current pipeline status. Updated on every event.

**`run_pipeline(live, message, username, source, request_id, gbc_id)`**
The core function every message passes through:
1. Updates dashboard to `TRIAGING...`
2. Calls `get_ai_config()` — reads AI and triage settings fresh from `.env`
3. Calls `is_relevant()` — AI triage decides if message is tactically relevant. If not, discards with status `FILTERED — NOT TACTICAL`
4. Updates dashboard to `THINKING...`
5. Calls `get_battle_assessment()` — full AI assessment, returns battle JSON
6. Calls `log_writer.write()` — saves to local log file
7. Calls `db_writer.insert()` — saves to PostgreSQL (only if DB credentials set)
8. Calls `gbc_api_client.push()` — POSTs to GBC API (only if `GBC_API_URL` set)
9. POSTs to config server dashboard for browser UI update
10. Validates against `PaeOutput` schema and POSTs to orchestrator `/paeoutputs`
11. Updates terminal dashboard with result

**`on_irc_message(live, username, message)`**
Callback registered with the IRC listener. Called for every message from any monitored channel. Generates a new `request_id` and calls `run_pipeline()`.

**`on_sse_event(live, event)`**
Callback registered with `PaeSseClient`. Called for every `PaeInputCreated` SSE event from the orchestrator. Extracts the message from `event.pae_input.track_id` and calls `run_pipeline()` using the orchestrator's `requestId` and `originator` directly.

---

### `pae_config.py` — Configuration

**Module-level constants**
All loaded from `.env` at startup: `IRC_SERVER`, `IRC_PORT`, `IRC_CHANNEL`, `IRC_NICKNAME`, `AI_ENDPOINT`, `AI_MODEL`, `AI_API_KEY`, `AI_TIMEOUT`, `TRIAGE_ENDPOINT`, `TRIAGE_MODEL`, `TRIAGE_TIMEOUT`, `ORCHESTRATOR_BASE_URL`, `ORCHESTRATOR_API_KEY`, `GBC_API_URL`, `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT`.

**`_detect_provider(url) → str`**
Returns `"nanogpt"` if the URL contains `nano-gpt.com`, otherwise `"lmstudio"`. Provider is auto-detected from the URL — no separate flag needed.

**`get_ai_config() → dict`**
Reads `.env` fresh from disk on every call using `dotenv_values()`. Bypasses Python's module cache so config UI changes take effect on the next message without restarting. Returns a dict with `provider`, `url`, `model`, `api_key`, `timeout`, `triage_url`, `triage_model`, and `triage_timeout`. If `TRIAGE_ENDPOINT` is blank, `triage_url` falls back to the main `AI_ENDPOINT`.

---

### `pipeline/triage.py` — AI Triage Filter

Replaces the old character-count filter with a real AI judgement. Stage 1 of the two-stage pipeline.

**`TRIAGE_PROMPT`**
The system prompt sent to the triage AI. Defines what counts as tactically relevant (military units, coordinates, weapons, orders, intelligence reports, brevity codes) and what counts as noise (casual chat, IRC bot output, test messages). Instructs the model to return only `{"relevant": true}` or `{"relevant": false, "reason": "..."}`.

**`is_relevant(message, triage_url, triage_model, api_key, timeout) → bool`**
Sends the message to the triage AI and returns `True` if relevant, `False` if noise. Uses `temperature: 0` for fast deterministic responses. Strips markdown fences and extracts the JSON object from the response. Fail-open design — returns `True` on any error (timeout, connection failure, bad JSON) so messages are never silently lost due to triage failures. Prints `TRIAGE: RELEVANT` or `TRIAGE: NOISE` with the reason to the terminal.

---

### `ai/agent.py` — Full AI Assessment Engine

**`BATTLE_DICTIONARY`**
Four categories of approved tactical verbs: `ATTACK`, `INVESTIGATE`, `DEGRADE`, `RESCUE`. The AI must choose all three effect operators exclusively from this list.

**`ALL_VERBS`**
Flat list of all 153 approved verbs across all categories. Used for prompt injection and response validation.

**`_load_csv_rows(filepath) → list`**
Reads a CSV file once at import time and returns all rows. Missing files print a warning and return empty — the app never crashes due to a missing CSV.

**`_ALL_ROWS`**
Dict holding all rows from all three reference CSVs, loaded once at module import. Never re-read from disk during operation.

**`_get_relevant_context(msg) → str`**
Scans all three CSV tables for rows matching words or two-word pairs from the message. Returns only matching rows, capped at 5 per table. If nothing matches, returns a note telling the model to use tactical judgment. Keeps the prompt lean — only sends relevant reference material.

**`_build_system_prompt(msg) → str`**
Assembles the complete system prompt: rules, full verb list, strict JSON output format, and the per-message CSV context from `_get_relevant_context()`.

**`get_battle_assessment(msg_content, username, request_id, lm_url, lm_model, timeout, provider, api_key) → list`**
The main assessment function. Builds the API payload, adds `Authorization` header for NanoGPT, sends the request, parses the response, validates all three `effectOperator` values against `ALL_VERBS`, and ensures every `opsLimits` entry has `battleEntity` populated (injects `"Unspecified"` if missing). Always sets `"originator": "rhino"` regardless of the IRC sender. Returns a full battle JSON list. Falls back to an error record on any failure so the pipeline always continues.

---

### `irc/listener.py` — IRC Bot

**`_read_irc_config() → dict`**
Reads `IRC_SERVER`, `IRC_PORT`, `IRC_CHANNEL`, and `IRC_NICKNAME` fresh from `.env` on every call. Enables live channel switching from the config UI — changes take effect on the next reconnect.

**`start(server, port, channel, on_message, retry_delay, nickname)`**
Connects to the IRC server and joins all channels listed in `IRC_CHANNEL` (comma-separated). Calls `on_message(username, message)` for every `PRIVMSG` received. Sends `PONG` to keep the connection alive. Reconnects automatically on any failure, re-reading config from `.env` each time so IRC settings updated in the UI take effect without a restart.

---

### `client/pae_sse_client.py` — SSE Listener

**`PaeSseClient.start(on_event)`**
Starts the background SSE listener thread. Connects to `ORCHESTRATOR_BASE_URL/paeinputs-sse` and listens for `PaeInputCreated` events.

**`PaeSseClient.stop()`**
Signals the listener to exit on next iteration.

**`PaeSseClient._listen_loop()`**
Daemon thread. Opens a streaming GET to the SSE endpoint. Reconnects automatically after `SSE_RETRY_DELAY` seconds on any failure.

**`PaeSseClient._process_stream(resp)`**
Parses SSE wire format. Handles `event:`, `data:`, blank line separators, and `: heartbeat` comments.

**`PaeSseClient._dispatch(event_name, raw_data)`**
Validates event name, parses JSON, validates against `PaeInputCreated` schema, and calls the registered handler.

---

### `client/http_client.py`

**`get_http_client() → httpx.Client`**
Returns an `httpx.Client` configured with `ORCHESTRATOR_BASE_URL` and the `X-API-Key` header. Used by all orchestrator communication.

---

### `client/pae_output_client.py`

**`submit(pae: PaeOutput) → PaeOutput`**
POSTs a validated `PaeOutput` to the orchestrator's `/paeoutputs`. Prints the full 422 rejection body if the orchestrator rejects the payload.

**`get_by_id(pae_id) → PaeOutput | None`**
Fetches a PAE output from the orchestrator by ID.

**`update(pae_id, pae) → PaeOutput`**
Updates an existing PAE output on the orchestrator.

---

### `output/log_writer.py`

**`write(tactical_json, log_path)`**
Appends the full battle JSON as a single line to `tactical_output.log`. Always runs. Local backup of every assessment.

---

### `output/db_writer.py`

**`insert(tactical_json, db_host, db_name, db_user, db_password, db_port) → bool`**
Inserts one battle JSON record as a new row into the `pae_data` table. `psycopg2` is imported lazily inside the function so a missing or unreachable database never crashes the app. Always an `INSERT` — never an `UPDATE`. Only called when all four DB credentials are present in `.env`.

---

### `output/gbc_api_client.py`

**`push(tactical_json, api_url, timeout) → bool`**
POSTs the complete battle JSON exactly as produced by the AI to the GBC API endpoint. Nothing is stripped or mapped — the full record is sent. Only called when `GBC_API_URL` is set in `.env`. Returns `True` on success, `False` on any failure.

---

### `schemas/pae_schemas.py` — Orchestrator Data Contracts

Pydantic models defining the exact shape of data exchanged with the orchestrator. All fields use camelCase aliases. Validators coerce bad AI output into safe types.

**`OpsLimit`** — `description`, `battleEntity`, `stateHypothesis` — all optional with coercion.

**`GoalContribution`** — `battleGoal`, `effect`.

**`PaeEffect`** — one battle effect slot: `id`, `effectOperator`, `description`, `timeWindow`, `stateHypothesis`, `opsLimits`, `goalContributions`, `recommended`, `ranking`.

**`PaeOutput`** — the full assessment record: `id`, `label`, `description`, `requestId`, `gbcId`, `entitiesOfInterest`, `battleEntity`, `battleEffects`, `chat`, `isDone`, `originator`, `lastUpdated`.

**`PaeInput`** — SSE trigger payload: `gbcId`, `requestId`, `trackId`, `originator`.

**`PaeInputCreated`** — SSE envelope: `{ "paeInput": { ... } }`.

---

### `config_server.py` — Web UI Server

FastAPI app on port 8080 serving the config editor and live dashboard.

**`read_env() → dict`**
Parses `.env` and returns all key-value pairs.

**`write_env(updates)`**
Writes updated values to `.env` in place, preserving comments and ordering.

**`detect_provider(url) → str`**
Detects `"nanogpt"` or `"lmstudio"` from the URL.

**`GET /`** — Config editor. Status panel, all editable fields, Save/Reset buttons. AI Endpoint field shows a live hint for the detected provider.

**`GET /dashboard`** — Live assessment dashboard. Live feed (last 3 auto-expanded) and full scrollable history. Full battle JSON per card including verbs, justifications, time windows, entities, and ops limits.

**`GET /env`** — Returns current `.env` values for all editable fields.

**`POST /env`** — Writes field updates to `.env`. Only accepts keys defined in `EDITABLE_FIELDS`.

**`GET /status`** — Returns orchestrator URL, AI provider/model, IRC server/channel, database status.

**`POST /assessment`** — Receives completed battle JSON from `main.py`. Stores in memory (max 200) and broadcasts to all connected dashboard clients.

**`GET /assessments`** — Returns full in-memory assessment history as a JSON array.

**`GET /json`** — Serves the raw JSON viewer page. Same SSE stream as the dashboard — every new assessment appears instantly.

**`GET /assessments/sse`** — SSE stream for the dashboard and JSON viewer. Pushes each new assessment to connected browsers in real time. Heartbeat every 15 seconds.

**`GET /json`** — Raw JSON viewer page. Shows every assessment as a collapsible, syntax-highlighted JSON record. Includes a Copy button per record and a Copy Latest button in the toolbar.

---

### `tests/emulator/pae_combined_emulator.py` — Fake Orchestrator

**`POST /paeinputs`** — Fires a `PaeInputCreated` SSE event. Use this to test reassessment triggers.

**`GET /paeinputs-sse`** — SSE stream your PAE app connects to.

**`POST /paeoutputs`** — Receives completed assessments from your PAE app.

**`GET /paeoutputs`** — Returns all stored assessments. Verify your app submitted correctly here.

**`GET /docs`** — Swagger UI for manual endpoint testing.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# IRC
IRC_SERVER=10.5.185.72
IRC_PORT=6667
IRC_CHANNEL=#app_dev,#ops
IRC_NICKNAME=PAE_Bot

# Triage — fast AI pre-filter before full assessment
# Leave TRIAGE_ENDPOINT blank to use the same endpoint as AI_ENDPOINT
TRIAGE_ENDPOINT=
TRIAGE_MODEL=gpt-4o-mini
TRIAGE_TIMEOUT=10

# AI — paste LM Studio or NanoGPT URL, provider auto-detected
AI_ENDPOINT=https://nano-gpt.com/api/v1/chat/completions
AI_MODEL=gpt-4o-mini
AI_API_KEY=sk-nano-your-key-here
AI_TIMEOUT=60

# Orchestrator
ORCHESTRATOR_BASE_URL=http://10.5.185.29:3016
ORCHESTRATOR_API_KEY=your-api-key

# GBC API
GBC_API_URL=http://10.5.185.29:3016/paeoutputs

# Database (optional — leave blank to skip DB writes)
DB_HOST=10.5.185.53
DB_NAME=shooca_db
DB_USER=shooca
DB_PASSWORD=your-password
DB_PORT=5432
```

### 3. Run locally

```bash
python main.py
```

---

## Docker

```bash
docker-compose up --build
```

| Service | Container | Port | Purpose |
|---|---|---|---|
| `emulator` | `pae_emulator` | `3016` | Fake orchestrator for testing |
| `pae` | `pae_app` | — | Main PAE application |
| `config` | `pae_config` | `8080` | Config editor + live dashboard |

**Docker note:** when running in Docker use `host.docker.internal` for LM Studio:
```env
AI_ENDPOINT=http://host.docker.internal:4334/v1/chat/completions
```

---

## Web UI — `http://localhost:8080`

**Config (`/`)** — edit all settings live. Changes write to `.env` immediately. No restart needed for AI provider, triage model, orchestrator URL, or IRC channel changes.

**Dashboard (`/dashboard`)** — real-time view of every assessment. Live feed shows last 3 auto-expanded. History shows everything since the server started.

**JSON Viewer (`/json`)** — displays the full raw battle JSON for every assessment with syntax highlighting. Keys in cyan, strings in green, numbers in orange, booleans in purple. Each record is collapsible. Copy button per record copies that JSON to clipboard. Copy Latest grabs the most recent. Receives new assessments live via SSE.

Terminal status values:
- `TRIAGING...` — triage AI call in progress
- `FILTERED — NOT TACTICAL` — triage rejected the message
- `THINKING...` — triage passed, full assessment running
- `COMPLETED — <label>` — assessment finished and submitted

All completed assessments are visible immediately in the JSON tab at `http://localhost:8080/json`.

---

## Connecting to Production

Update two values in `.env` or the config UI:

```env
ORCHESTRATOR_BASE_URL=http://10.5.185.29:3016
ORCHESTRATOR_API_KEY=your-real-api-key
```

The SSE client reconnects automatically within `SSE_RETRY_DELAY` seconds.

---

## AI Models

| Model | Endpoint | Notes |
|---|---|---|
| Gemma 4 E4B | `http://host.docker.internal:4334/v1/chat/completions` | Local, fast |
| Gemma 4 31B | Same + change `AI_MODEL` | Local, more capable |
| GPT-4o Mini | `https://nano-gpt.com/api/v1/chat/completions` | Cloud, fast, ideal for triage |
| GPT-4o | `https://nano-gpt.com/api/v1/chat/completions` | Cloud, most capable |

Switch providers by changing `AI_ENDPOINT` in the config UI — no restart needed.

---

## Key Behaviour Notes

- All messages pass through AI triage before reaching full assessment — casual chat, IRC noise, and off-topic messages are discarded
- Triage is fail-open — any error (timeout, connection failure) treats the message as relevant so nothing is silently lost
- The full AI assessment must choose verbs exclusively from the approved battle dictionary (153 verbs across 4 categories: ATTACK, INVESTIGATE, DEGRADE, RESCUE)
- CSV reference tables are looked up per-message — only rows matching words in the message are sent (max 5 per table) to keep the prompt lean
- `originator` is always set to `"rhino"` regardless of who sent the IRC message
- If the AI omits `battleEntity` from `opsLimits`, `"Unspecified"` is injected automatically before submission
- All assessments are written to `tactical_output.log` locally regardless of any other output status
- DB writes are skipped if `DB_HOST` is not set — no errors
- GBC API pushes are skipped if `GBC_API_URL` is not set — no errors
- The IRC bot reconnects automatically and re-reads channel settings from `.env` on each reconnect
- The dashboard stores up to 200 assessments in memory — resets if the config container restarts
- Multiple IRC channels are supported — comma-separate them in `IRC_CHANNEL`

```
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⣾⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠀⢂⠀⠀⠀⠀⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⣿⠀
⠀⠀⠀⠀⠀⠀⢀⡈⠛⠦⠀⠀⠀⠆⠀⠀⠀⠀⡀⠀⠐⠀⠀⠀⠀⠀⠀⡛⢱⣿⣿⠀
⠀⠀⠀⠠⣤⣴⠝⢛⠂⠀⠀⣐⣤⣠⣤⣰⣤⣜⢀⠀⢀⠀⠀⠀⠀⠀⠀⡅⣸⣿⣿⠀
⠀⠀⠀⠀⢖⣂⠄⡀⣤⣶⣿⣿⣿⣿⣿⣿⣿⣿⣷⣦⡀⠀⠁⠀⠀⠀⠀⣇⣿⣿⣿⠀
⠀⠀⠀⠀⣤⣶⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢿⣿⣿⣶⣦⠀⠀⠀⠀⢹⠹⣿⣿⠀
⠀⠀⠀⣤⢻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢟⣽⡪⠽⠛⡛⠻⣿⣷⠠⠀⠀⠀⠀⢻⣿⠀
⠀⠀⠀⢦⣼⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠟⠁⣠⣶⣾⣷⣤⡘⢟⡣⠀⠀⠀⠀⠘⣿⠀
⠀⠀⠀⡞⠿⢿⣿⣿⣿⣿⡿⣿⡿⠋⠀⣠⠾⣻⣽⠾⠻⣿⣿⡜⡷⡀⠀⠀⠀⢶⣿⠀
⠀⠀⠀⢠⣶⣤⣄⣀⠉⠻⢿⣶⡏⣡⡾⠗⣩⡀⣀⣶⣶⣾⣿⣿⡸⣧⠀⣢⠄⠸⣿⠀
⠀⠀⠀⠘⣿⠿⠛⠋⠋⠝⡃⣿⣿⣬⡻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡄⢰⡹⣼⠀⢿⠀
⠀⠀⠀⠀⣯⡰⣗⣴⣾⣿⢡⢹⣿⣎⢷⣽⣿⣿⣿⣿⣿⣿⣿⣿⣿⡁⢸⣛⡟⠀⣾⠀
⠀⠀⠀⠀⣿⣿⣿⣿⣿⣿⡏⢸⣿⣿⣎⠿⣿⣿⣿⣿⣿⣿⣿⡿⢹⣿⠀⠉⠀⣴⣿⠀
⠀⠀⠀⠀⠸⣿⣿⣿⣿⣿⡟⣿⣿⣿⣿⣿⡌⣿⣿⣿⣿⣿⡟⢠⣿⣿⠀⠀⠀⠉⢸⠀
⠀⠀⠀⠀⠀⠹⣿⣿⣿⣿⣏⠌⠋⣩⡶⣒⣵⣿⣿⣿⣿⣿⣷⣿⣿⣿⠀⠀⠀⠀⢸⠀
⠀⠀⠀⠀⠀⠀⠈⠙⢛⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠟⣻⣿⣿⣿⣿⡟⡄⢀⠀⠀⠈⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠐⢝⢿⣿⡛⢯⡶⢶⣒⣛⣧⣾⢿⣿⣿⣿⡿⢡⣿⠈⢧⡀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⡐⣶⣾⣿⣿⣿⠿⣻⣻⣿⣿⣿⡿⢡⣿⣿⡇⠆⢧⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢨⣭⣭⣥⣶⣾⣿⣿⣿⣿⡟⣡⣿⣿⣿⣿⢰⢸⡖⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⢊⡾⡁⠻⣿⣿⣿⣿⣿⣿⣿⠏⣰⣿⣿⣿⣿⣿⣼⡟⣿⠀
⠀⠀⠀⠀⠀⠀⠀⡠⣠⢳⣧⡺⠁⡄⣝⡻⠿⠿⠿⢛⣡⣾⣿⣿⣿⣿⣿⣿⢻⣧⣿⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
```
