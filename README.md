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

A tactical AI microservice that listens to J-chat messages from IRC and reassessment triggers from an orchestrator cluster via SSE. Every message is assessed by an AI, which assigns three prioritised effect operator verbs and populates a full battle JSON record. Results are pushed to the GBC API, the orchestrator, and optionally a PostgreSQL database.

---

## How It Works — The Full Pipeline

Every message that arrives — whether from IRC or an SSE trigger — passes through the same pipeline:

```
Input (IRC or SSE)
    │
    ▼
pipeline/filter.py       — noise filter (too short, garbled = discarded)
    │
    ▼
ai/agent.py              — AI assessment (NanoGPT or LM Studio)
    │
    ▼
output/log_writer.py     — always writes to tactical_output.log
output/db_writer.py      — inserts to PostgreSQL (if DB configured)
output/gbc_api_client.py — POSTs to GBC API endpoint (if configured)
config_server.py         — pushes to live dashboard
client/pae_output_client.py — POSTs to orchestrator /paeoutputs
```

There are two input paths:

**Path 1 — IRC** — the bot joins your J-chat channel and listens for messages in real time. Every message from any user is picked up and run through the pipeline.

**Path 2 — SSE** — the orchestrator pushes a `PaeInputCreated` event to your app when another application in the cluster wants a message reassessed. The `trackId` field in that event contains the message text.

Both paths call the exact same `run_pipeline()` function. The only difference is where the message came from.

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
│   └── agent.py                   # AI assessment engine
│
├── client/
│   ├── http_client.py             # Shared HTTP client for orchestrator
│   ├── pae_sse_client.py          # SSE listener — receives retrigger events
│   └── pae_output_client.py       # POSTs completed assessments to orchestrator
│
├── irc/
│   └── listener.py                # IRC bot — connects, joins channels, reads messages
│
├── pipeline/
│   ├── filter.py                  # Message noise filter
│   └── builder.py                 # Generates unique request IDs
│
├── output/
│   ├── log_writer.py              # Writes assessments to local log file
│   ├── db_writer.py               # Inserts assessments into PostgreSQL
│   ├── gbc_api_client.py          # Maps and POSTs to the GBC API endpoint
│   └── api_push.py                # Generic API push (legacy — use gbc_api_client)
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

The top-level orchestrator. Starts all listeners and defines the pipeline.

**`make_dashboard(...) → Table`**
Builds the Rich terminal table that shows live activity. Displays timestamp, source (IRC/SSE), the raw message, the three AI verbs, and the current status. Called on every pipeline event to keep the terminal view current.

**`run_pipeline(live, message, username, source, request_id, gbc_id)`**
The core function. Every message from every source passes through here in order:
1. Runs `is_clean()` — discards noise
2. Calls `get_ai_config()` — reads the current AI provider and URL fresh from `.env`
3. Calls `get_battle_assessment()` — sends message to AI, gets battle JSON back
4. Calls `log_writer.write()` — saves to local log file
5. Calls `db_writer.insert()` — saves to PostgreSQL (only if DB credentials set)
6. Calls `gbc_api_client.push()` — POSTs to GBC API (only if `GBC_API_URL` set)
7. POSTs to `config_server` dashboard — updates the browser UI
8. Validates against `PaeOutput` schema and POSTs to orchestrator `/paeoutputs`
9. Updates the terminal dashboard

**`on_irc_message(live, username, message)`**
Callback registered with the IRC listener. Called every time a message arrives from any monitored IRC channel. Generates a fresh `request_id` and hands off to `run_pipeline()`.

**`on_sse_event(live, event)`**
Callback registered with `PaeSseClient`. Called every time the orchestrator sends a `PaeInputCreated` SSE event. Extracts the message text from `event.pae_input.track_id` and hands off to `run_pipeline()` using the `requestId` and `originator` from the SSE payload directly.

---

### `pae_config.py` — Configuration

Loads settings from `.env` at startup. Also provides a live-reload function so the UI can change settings without restarting.

**Module-level constants**
`IRC_SERVER`, `IRC_PORT`, `IRC_CHANNEL`, `IRC_NICKNAME`, `AI_ENDPOINT`, `AI_MODEL`, `AI_API_KEY`, `AI_TIMEOUT`, `ORCHESTRATOR_BASE_URL`, `ORCHESTRATOR_API_KEY`, `GBC_API_URL`, `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT` — all loaded from `.env` once at startup via `load_dotenv()`.

**`_detect_provider(url) → str`**
Inspects the AI endpoint URL. If it contains `nano-gpt.com` returns `"nanogpt"`, otherwise returns `"lmstudio"`. This means you never have to set a separate provider flag — just paste the URL.

**`get_ai_config() → dict`**
Reads `.env` fresh from disk every time it is called using `dotenv_values()`. This bypasses Python's module cache so changes made in the config UI take effect on the very next message without restarting the container. Returns a dict with `provider`, `url`, `model`, `api_key`, and `timeout`.

---

### `ai/agent.py` — AI Assessment Engine

Handles everything related to sending a message to the AI and getting a structured battle JSON response back.

**`BATTLE_DICTIONARY`**
A dict of four categories (`ATTACK`, `INVESTIGATE`, `DEGRADE`, `RESCUE`), each containing a list of approved tactical verbs. The AI must choose its three effect operators exclusively from this list. If it returns anything outside the list it is replaced with `"NO PAE ACTION REQUIRED"`.

**`ALL_VERBS`**
A flat list of every verb across all four categories. Used to validate the AI's response and injected into the system prompt so the model knows exactly which words it is allowed to use.

**`_load_csv_rows(filepath) → list`**
Reads a single CSV file and returns all rows as a list of lists. Called once at import time for each of the three reference CSVs. If a file is not found it prints a warning and returns an empty list so the app still runs.

**`_ALL_ROWS`**
A dict holding all rows from all three CSVs, loaded once at module import. Keys are human-readable labels used in the prompt. This avoids re-reading files from disk on every assessment call.

**`_get_relevant_context(msg) → str`**
Given a message, extracts individual words and two-word pairs, then scans all three CSV tables for matching rows. Returns only the matching rows — capped at 5 per table — formatted as pipe-delimited text blocks. If nothing matches it returns a note telling the model to use its tactical judgment. This keeps the prompt small and fast — sending the full 300-row CSV on every call would be wasteful and slow.

**`_build_system_prompt(msg) → str`**
Assembles the complete system prompt for the AI call. Contains the rules, the full approved verb list, the strict JSON output format, and the per-message CSV context from `_get_relevant_context()`. The verb list and rules are the same every call — only the CSV context block at the bottom changes.

**`get_battle_assessment(msg_content, username, request_id, lm_url, lm_model, timeout, provider, api_key) → list`**
The main public function. Sends the message to the configured AI provider and returns a fully populated battle JSON list. Internally it builds the payload, adds an `Authorization` header for NanoGPT, sends the request, strips any markdown code fences, extracts the JSON object, validates all three `effectOperator` values against `ALL_VERBS`, and ensures every `opsLimits` entry has `battleEntity` populated (injects `"Unspecified"` if the AI left it blank). Returns an error record if anything fails so the pipeline always continues.

---

### `irc/listener.py` — IRC Bot

**`_read_irc_config() → dict`**
Reads `IRC_SERVER`, `IRC_PORT`, `IRC_CHANNEL`, and `IRC_NICKNAME` directly from `.env` on every call. Used at the top of each reconnect attempt so changes made in the config UI take effect on the next reconnect without restarting the container.

**`start(server, port, channel, on_message, retry_delay, nickname)`**
Connects to the IRC server, joins one or more channels (comma-separated), and listens indefinitely. On every `PRIVMSG` line it extracts the username and message text and calls `on_message(username, message)`. Sends `PONG` responses to keep the connection alive. If the connection drops or fails for any reason it waits `retry_delay` seconds and reconnects automatically. IRC settings are re-read from `.env` on every reconnect so a channel change in the UI takes effect on the next reconnect.

---

### `client/pae_sse_client.py` — SSE Listener

Connects to the orchestrator's `/paeinputs-sse` stream in a background daemon thread and listens for `PaeInputCreated` events.

**`PaeSseClient.start(on_event)`**
Starts the background SSE listener thread. Idempotent — safe to call multiple times. Registers `on_event` as the handler for incoming events.

**`PaeSseClient.stop()`**
Signals the listener loop to exit on the next iteration. Called on `KeyboardInterrupt` shutdown.

**`PaeSseClient._listen_loop()`**
Runs on the daemon thread. Opens a streaming GET connection to `/paeinputs-sse`. If it disconnects for any reason it waits `SSE_RETRY_DELAY` seconds and reconnects automatically.

**`PaeSseClient._process_stream(resp)`**
Parses the SSE wire format line by line. Named events arrive as `event: PaeInputCreated` followed by `data: {...}`. Blank lines are message separators. Heartbeat comments (`: heartbeat`) are ignored.

**`PaeSseClient._dispatch(event_name, raw_data)`**
Validates the event name, parses the JSON payload, validates it against the `PaeInputCreated` Pydantic schema, and calls the registered handler. Also pushes to a UI queue for monitoring.

---

### `client/http_client.py` — Shared HTTP Client

**`get_http_client() → httpx.Client`**
Returns a configured `httpx.Client` pointed at `ORCHESTRATOR_BASE_URL` with the `X-API-Key` header set. Used by both `pae_output_client.py` and `pae_input_client.py` so the orchestrator connection is configured in one place.

---

### `client/pae_output_client.py` — Orchestrator Output

**`submit(pae: PaeOutput) → PaeOutput`**
POSTs a completed and schema-validated `PaeOutput` to the orchestrator's `/paeoutputs` endpoint. If the orchestrator returns a 422 (validation error) it prints the full rejection detail so you can see exactly which field failed. Returns the stored record as confirmed by the orchestrator.

**`get_by_id(pae_id) → PaeOutput | None`**
Fetches an existing PAE output from the orchestrator by ID. Returns `None` if not found.

**`update(pae_id, pae) → PaeOutput`**
Updates an existing PAE output on the orchestrator via PUT.

---

### `pipeline/filter.py` — Noise Filter

**`is_clean(text) → bool`**
Returns `True` only if the message looks like a real tactical transmission. Strips everything except alphanumeric characters and spaces, then checks that there are at least 2 distinct words and the cleaned text is at least 6 characters long. Filters out single words, IRC bot commands, garbled binary strings, and empty lines. Messages that fail this check are discarded before ever reaching the AI.

---

### `pipeline/builder.py` — Request ID Generator

**`make_request_id() → str`**
Generates a unique `track-XXXXXX` string using `uuid4` for every new IRC message assessment. SSE reassessments use the `requestId` from the SSE payload directly rather than generating a new one.

---

### `output/log_writer.py` — Local Log

**`write(tactical_json, log_path)`**
Appends the completed battle JSON as a single line to `tactical_output.log` at the project root. Always runs regardless of orchestrator or database availability. Serves as a local backup of every assessment ever made. Each line is a complete self-contained JSON record.

---

### `output/db_writer.py` — PostgreSQL Writer

Only runs when `DB_HOST`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` are all set in `.env`. `psycopg2` is imported lazily inside the function so a missing or unreachable database never crashes the app at startup.

**`insert(tactical_json, db_host, db_name, db_user, db_password, db_port) → bool`**
Inserts one battle JSON record as a new row in the `pae_data` table. Always an `INSERT` — never an `UPDATE` — so the original record is preserved alongside any reassessments. Stores `request_id`, `originator`, `label`, `description`, the raw message, and the full JSON blob in a `JSONB` column called `payload`. Returns `True` on success, `False` on any failure.

---

### `output/gbc_api_client.py` — GBC API Output

Maps PAE battle JSON to the GBC API schema and POSTs it. Only runs when `GBC_API_URL` is set in `.env`.

**`_map_to_gbc_schema(record) → dict`**
Translates a PAE battle JSON record into the GBC output schema. The mapping is:

| PAE field | GBC field |
|---|---|
| `requestId` | `id` |
| `label` | `label` |
| `isDone` | `isArchived` / `status` |
| `description` | `mission` |
| `lastUpdated` | `lastUpdate` |
| `chat[0]` | `eventDetails[].information` |
| `battleEffects` | `targets[]` |
| `effectOperator` | `targets[].actions[].verb` |
| `description` | `targets[].actions[].justification` |
| `timeWindow` | `targets[].actions[].timingInfo` |
| `opsLimits` presence | `hasOperationalConstraint` |
| — | `latitude`, `longitude` = `0.0` |
| — | `eventType`, `alertType` = `0` |

**`push(tactical_json, api_url, timeout) → bool`**
Calls `_map_to_gbc_schema()`, prints the payload for debugging, and POSTs it to the GBC API. Returns `True` on success, `False` on timeout, connection error, or HTTP error.

---

### `schemas/pae_schemas.py` — Data Contracts

Pydantic models provided by the DB manager that define the exact shape of data exchanged with the orchestrator. All fields use camelCase aliases matching the orchestrator's JSON. Validators coerce bad AI output (empty lists, `None` values) into safe types so validation never crashes the pipeline.

**`OpsLimit`** — one operational constraint: `description`, `battleEntity`, `stateHypothesis`. All optional with coercion.

**`GoalContribution`** — links an effect to a battle goal: `battleGoal`, `effect`.

**`PaeEffect`** — one battle effect slot: `id`, `effectOperator`, `description`, `timeWindow`, `stateHypothesis`, `opsLimits`, `goalContributions`, `recommended`, `ranking`.

**`PaeOutput`** — the full assessment record POSTed to the orchestrator: `id`, `label`, `description`, `requestId`, `gbcId`, `entitiesOfInterest`, `battleEntity`, `battleEffects`, `chat`, `isDone`, `originator`, `lastUpdated`.

**`PaeInput`** — the trigger payload received from the orchestrator SSE stream: `gbcId`, `requestId`, `trackId`, `originator`.

**`PaeInputCreated`** — wrapper around `PaeInput` matching the orchestrator's SSE envelope: `{ "paeInput": { ... } }`.

---

### `config_server.py` — Web UI Server

A FastAPI application running on port 8080. Serves two browser pages and several API endpoints.

**`read_env() → dict`**
Reads and parses the `.env` file, returning all key-value pairs. Used by the `/env` endpoint to populate the config form fields.

**`write_env(updates)`**
Writes updated values back to `.env` in place. Preserves all existing lines, comments, and ordering. Only modifies the keys provided in `updates`. Appends new keys if they don't already exist in the file.

**`detect_provider(url) → str`**
Same logic as `pae_config._detect_provider()` — checks if the URL contains `nano-gpt.com`. Used to show which AI provider is active in the status panel.

**`GET /`**
Serves the config editor page. Shows a status panel (orchestrator, AI provider, IRC, database), editable fields for all configurable settings, and a Save/Reset button pair. Fields highlighted orange when modified. The AI Endpoint field shows a live hint indicating whether LM Studio or NanoGPT was detected.

**`GET /dashboard`**
Serves the live assessment dashboard. Shows a live feed of the last 3 assessments (auto-expanded) and a full scrollable history. Each card shows the original message, AI label, description, all three battle effects with verbs/justifications/time windows, entities of interest, and ops limits. Connects to the server via SSE for real-time updates.

**`GET /env`**
Returns current `.env` values for all editable fields as JSON. Used by the config page to populate form inputs on load.

**`POST /env`**
Accepts a JSON body of `{ "values": { "KEY": "value" } }` and writes the changes to `.env`. Only keys defined in `EDITABLE_FIELDS` are accepted — all others are ignored for safety.

**`GET /status`**
Returns current runtime config for the status panel: orchestrator URL, AI provider and model, IRC server and channel, database connection status.

**`POST /assessment`**
Receives completed battle JSON from `main.py` after every assessment. Stores it in an in-memory deque (max 200 records) and broadcasts it to all connected dashboard clients via SSE.

**`GET /assessments`**
Returns the full in-memory assessment history as a JSON array. Called by the dashboard on page load to populate the history section.

**`GET /assessments/sse`**
SSE stream endpoint. Dashboard clients connect here and receive a push notification for every new assessment as it arrives. Sends a heartbeat comment every 15 seconds to keep the connection alive.

---

### `tests/emulator/pae_combined_emulator.py` — Fake Orchestrator

A FastAPI server that mimics the production orchestrator for local testing. Runs on port 3016.

**`POST /paeinputs`** — accepts a trigger payload and broadcasts a `PaeInputCreated` SSE event to all connected listeners. This is how you fire a test reassessment.

**`GET /paeinputs-sse`** — the SSE stream your PAE app connects to. Emits `PaeInputCreated` events when `/paeinputs` is called.

**`POST /paeoutputs`** — receives completed assessments from your PAE app and stores them in memory.

**`GET /paeoutputs`** — returns all stored assessments. Check here after a test to confirm your app submitted correctly.

**`GET /docs`** — Swagger UI for clicking through all endpoints manually.

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

# AI — paste LM Studio or NanoGPT URL, provider auto-detected
AI_ENDPOINT=https://nano-gpt.com/api/v1/chat/completions
AI_MODEL=gpt-4o-mini
AI_API_KEY=sk-nano-your-key-here
AI_TIMEOUT=60

# Orchestrator
ORCHESTRATOR_BASE_URL=http://10.5.185.XX:PORT
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

**Docker note:** when running in Docker, LM Studio runs on your host machine. Use `host.docker.internal`:
```env
AI_ENDPOINT=http://host.docker.internal:4334/v1/chat/completions
```

---

## Web UI — `http://localhost:8080`

**Config page (`/`)** — edit all settings live. Changes write to `.env` immediately and take effect on the next message. No restart needed for AI provider, orchestrator URL, or IRC channel changes.

**Dashboard (`/dashboard`)** — real-time view of every assessment. Live feed shows the last 3 auto-expanded. History shows everything since the server started.

---

## Connecting to Production

To switch from the emulator to the real orchestrator, update two values in `.env` or the config UI:

```env
ORCHESTRATOR_BASE_URL=http://10.5.185.XX:PORT
ORCHESTRATOR_API_KEY=your-real-api-key
```

The SSE client reconnects automatically within `SSE_RETRY_DELAY` seconds.

---

## AI Models

| Model | Endpoint value | Notes |
|---|---|---|
| Gemma 4 E4B | `http://host.docker.internal:4334/v1/chat/completions` | Local, fast |
| Gemma 4 31B | `http://host.docker.internal:4334/v1/chat/completions` + change `AI_MODEL` | Local, more capable |
| GPT-4o Mini | `https://nano-gpt.com/api/v1/chat/completions` | Cloud, fast, good JSON |
| GPT-4o | `https://nano-gpt.com/api/v1/chat/completions` | Cloud, most capable |

Switch providers by changing `AI_ENDPOINT` in the config UI — no restart needed.

---

## Key Behaviour Notes

- Messages under 2 words or 6 characters are filtered as noise before reaching the AI
- The AI must choose verbs exclusively from the approved battle dictionary (153 verbs across 4 categories)
- CSV reference tables are looked up per-message — only rows matching words in the message are sent to the AI (max 5 rows per table) to keep the prompt lean
- If the AI returns nothing the record is marked `NO PAE ACTION REQUIRED`
- If the AI omits `battleEntity` from `opsLimits`, the value `"Unspecified"` is injected automatically before submission
- All assessments are written to `tactical_output.log` locally regardless of orchestrator or database availability
- The dashboard stores up to 200 assessments in memory — history resets if the config container restarts
- The IRC bot reconnects automatically if the server drops, and re-reads channel/nickname settings from `.env` on each reconnect
- DB writes are skipped entirely if `DB_HOST` is not set — no errors, no crashes
- GBC API pushes are skipped entirely if `GBC_API_URL` is not set

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