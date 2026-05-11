# PAE — Pre-emptive Action Engine

A real-time tactical AI microservice that ingests military J-chat IRC traffic and orchestrator SSE retriggers, classifies and enriches each message, runs a two-stage AI assessment, and pushes structured battle JSON to downstream systems.

```
┌────────────────────────────────────────────────────────────────┐
│                       PAE Pipeline                              │
└────────────────────────────────────────────────────────────────┘

   IRC bot ──────┐                  SSE retrigger ──────┐
                 │                                        │
                 ▼                                        ▼
        ┌─────────────────┐                ┌───────────────────────┐
        │ 1. AI Triage    │                │ 1. Format check       │
        │   (relevant?)   │                │   regex ^[A-Z]{2}\d+$ │
        └────────┬────────┘                └──────────┬────────────┘
                 │ relevant                            │ passes
                 ▼                                     ▼
                                          ┌───────────────────────┐
                                          │ 2. Track API validate │
                                          │   (track has data?)   │
                                          └──────────┬────────────┘
                                                     │ valid
                                                     ▼
        ┌────────────────────────────────────────────────────────┐
        │       3. Classify API enrichment                        │
        │       — callsigns + entities + tier                     │
        └────────────────────────┬───────────────────────────────┘
                                 ▼
        ┌────────────────────────────────────────────────────────┐
        │       4. AI battle assessment (battle JSON)             │
        └────────────────────────┬───────────────────────────────┘
                                 ▼
       ┌─────────────┬───────────┼──────────────┬─────────────────┐
       ▼             ▼           ▼              ▼                 ▼
    local log    DB (opt)    GBC API       Orchestrator        Config UI
                                                               Dashboard
```

---

## Quick Start

```bash
# 1. Configure
cp .env.example .env
# edit .env — set IRC_SERVER, AI_ENDPOINT, ORCHESTRATOR_BASE_URL at minimum

# 2. Build and run
docker-compose down
docker-compose build --no-cache
docker-compose up

# 3. Open the config UI
# http://localhost:8080
```

---

## Services

The Docker stack runs three services from a single image:

| Service | Port | Purpose |
|---|---|---|
| `pae` | – | Main pipeline: IRC listener + SSE listener + AI orchestration |
| `config` | 8080 | Web UI: configuration, dashboard, JSON viewer, classify feed |
| `emulator` | 3016 | Fake orchestrator for local testing — comment out for production |

---

## File Structure

```
pae/
├── main.py                    # Entry point — pipeline orchestration, IRC + SSE handlers
├── pae_config.py              # Settings loader with live .env reload
├── config_server.py           # FastAPI web UI on port 8080
├── Dockerfile                 # Single image for all services
├── docker-compose.yml
├── requirements.txt           # Python deps
├── .env / .env.example
│
├── ai/
│   └── agent.py               # Battle dictionary + prompt + AI call + JSON envelope
│
├── client/
│   ├── http_client.py         # Shared httpx client for orchestrator
│   ├── pae_sse_client.py      # SSE listener for PaeInputCreated events
│   └── pae_output_client.py   # POST to orchestrator /paeoutputs
│
├── irc/
│   └── listener.py            # IRC bot — multi-channel, auto-reconnect, live config
│
├── pipeline/
│   ├── triage.py              # Stage 1: AI relevance filter (fail-open)
│   ├── enricher.py            # Classify API + Track API
│   └── builder.py             # DDRR-rr request ID generator + track ID extractor
│
├── output/
│   ├── log_writer.py          # Local log file
│   ├── db_writer.py           # PostgreSQL INSERT (optional)
│   └── gbc_api_client.py      # POST to GBC API
│
├── schemas/
│   └── pae_schemas.py         # Pydantic v2 schema for PaeInput / PaeOutput
│
├── data/                      # Tactical reference CSVs
│   ├── standard_tactical_chat_abbreviations.csv
│   ├── tactical_glossary_abbreviations.csv
│   └── brevity_codes_2025_standard.csv
│
└── tests/emulator/
    ├── pae_combined_emulator.py   # FastAPI fake orchestrator
    └── pae_run_emulator.py        # Entry point — uvicorn on port 3016
```

---

## Configuration

All configuration lives in `.env`. Every field below is editable from the config UI at `http://localhost:8080`.

### IRC
```env
IRC_SERVER=10.5.185.72
IRC_PORT=6667
IRC_CHANNEL=#app_dev,#c2_coord     # comma-separated for multi-channel
IRC_NICKNAME=PAE_Bot_ShocN2
```

### AI — Battle Assessment
```env
AI_ENDPOINT=http://10.5.185.55:4334/v1/chat/completions
AI_MODEL=google/gemma-4-e4b
AI_API_KEY=                # required for NanoGPT, leave blank for LM Studio
AI_TIMEOUT=60
```

Provider is auto-detected from the URL — LM Studio for `:4334`-style internal URLs, NanoGPT for `nano-gpt.com`.

### AI — Triage
```env
TRIAGE_ENDPOINT=           # blank = reuse AI_ENDPOINT
TRIAGE_MODEL=google/gemma-4-e4b
TRIAGE_TIMEOUT=10
```

### Enrichment APIs
```env
CLASSIFY_API_URL=http://10.5.185.30:3060/classify
CLASSIFY_TIMEOUT=5

TRACK_API_URL=http://10.5.185.29:3021/tracks
TRACK_API_TIMEOUT=5
```

### Output Destinations
```env
ORCHESTRATOR_BASE_URL=http://emulator:3016    # use service name for docker-internal
ORCHESTRATOR_API_KEY=
SSE_RETRY_DELAY=5
GBC_API_URL=http://emulator:3016/paeoutputs

DB_HOST=10.5.185.21
DB_NAME=shooca_db
DB_USER=shooca
DB_PASSWORD=shooca222
DB_PORT=5432
```

### Test Run Identifier
```env
RUN_DAY=01           # DD in DDRR-rr request ID format
RUN_NUMBER=01        # RR in DDRR-rr
```

The request counter (`rr`) auto-increments per assessment and resets to 0 when `RUN_NUMBER` changes. Both can be set live from the config UI — no restart needed.

---

## How It Works

### IRC Path
1. IRC bot receives a chat message
2. **Triage** — fast AI call decides if the message is tactically relevant. Fail-open if AI is down.
3. **Classify API** — extracts callsigns, track numbers, entities, importance tier
4. **Track ID extraction** — regex pulls the first `XX###` pattern from the message text (TN700, TS016, etc.); `null` if none
5. **Battle assessment** — full AI call returns structured battle JSON with three effect slots
6. Each effect's `effectOperator` is validated against the approved verb dictionary; invalid verbs become `NO PAE ACTION REQUIRED`
7. Output is written to local log, DB (if configured), GBC API, and POSTed to orchestrator

### SSE Path
1. SSE listener receives a `PaeInputCreated` event with `trackId`
2. **Format check** — strip non-alphanumeric characters, must match `^[A-Za-z]{2}\d+$`. Rejects plain numbers like `44250` instantly.
3. **Track API** — fetches `{TRACK_API_URL}/{trackId}`. Rejects retrigger if response is empty or 404.
4. From here the pipeline runs identically to the IRC path
5. `gbcId` from the SSE event is included in output if supplied
6. `trackId` from the SSE event is always included in output

### Identifiers on each output

| Field | Format | Source |
|---|---|---|
| `id` | `pae-<8 hex chars>` | Generated per assessment |
| `requestId` | `DDRR-rr` | Generated from Day/Run config + auto-counter |
| `trackId` | `XX###` | SSE: from event. IRC: regex-extracted from message text |
| `gbcId` | string | SSE: from event. IRC: omitted |
| `battleEffects[i].id` | `<base id>-e0X` | Derived from the envelope `id` |

`gbcId` and `trackId` only appear in the JSON when they have a value — they are omitted entirely when null.

### Selecting `entitiesOfInterest` and `battleEntity`
Both fields contain a single-item list with the most important subject, picked in priority order:
1. Track number from classifier (most specific tactical identifier)
2. AI's first-listed entity from `entitiesOfInterest`
3. AI's first-listed entity from `battleEntity`
4. Named callsign from classifier (skipping `unknown:` prefixed)

---

## Config UI

Open `http://localhost:8080` to access four tabs:

- **Config** — edit any `.env` field with live save. Test Run panel for Day/Run + counter reset.
- **Dashboard** — live battle assessment cards as they arrive
- **JSON** — raw JSON viewer with syntax highlighting and copy buttons
- **Classify** — live feed of classify API responses with tier badges, callsigns, entities, reasoning

---

## Predicted Problems & Mitigations

### LM Studio rejects rapid-fire requests with 400
**Symptom:** First message succeeds, subsequent messages immediately return `400 Client Error` with empty body.

**Cause:** LM Studio's concurrent request limit (often 1) rejects new requests while one is in flight.

**Current mitigation:** `agent.py` retries once with a 3-second backoff on a 400.

**Better fixes:**
- Raise the concurrent request limit in LM Studio's settings on `10.5.185.55`
- Switch the assessment model to NanoGPT (keep triage on LM Studio for speed)
- Add a sequential queue in `main.py`

### Database column does not exist
**Symptom:** `WARNING: DB insert failed: column "X" of relation "pae_data" does not exist`

**Cause:** The actual `pae_data` table schema doesn't match what `db_writer.py` writes. The writer currently inserts: `originator, label, description, payload, message`.

**Fix:** Either add the missing column on the DB side, or update `output/db_writer.py` to match the actual columns. Confirm the schema with the DBA before changing either side.

**Current state:** DB writes fail silently and don't block the rest of the pipeline.

### Orchestrator returns 400 on ERROR records
**Symptom:** When the AI fails and PAE submits an ERROR record, the orchestrator returns `400 Bad Request`.

**Cause:** ERROR records contain `null` fields that the orchestrator's strict schema rejects.

**Fix options:**
- Suppress orchestrator submission when AI fails
- Fill error record fields with empty strings instead of nulls
- Coordinate with the orchestrator team

### Track API rejects valid tracks during outage
**Symptom:** Valid SSE retriggers rejected with `REJECTED — NO TRACK DATA` even though the track exists.

**Cause:** Track API at `10.5.185.29:3021` is unreachable or returning empty during a partial outage.

**Mitigation:** Set `TRACK_API_URL` to empty in the UI to skip validation. Toggling it off is a fast recovery option during a known outage.

### Classify API timeout under load
**Symptom:** `CLASSIFY: timed out after 5s — skipping enrichment.`

**Impact:** Assessment proceeds without callsign/entity enrichment. Battle JSON still generates but `entitiesOfInterest` will fall back to AI extraction only.

**Tuning:** Raise `CLASSIFY_TIMEOUT` if the API is slow but functional.

### LM Studio model unloads after idle
**Symptom:** First message after a long quiet period takes 30+ seconds; subsequent messages are normal.

**Cause:** LM Studio unloads idle models from GPU memory.

**Mitigation:** Configure LM Studio to keep the model loaded, or accept the cold-start delay. Default `AI_TIMEOUT=60` should accommodate it.

### IRC bot disconnects silently
**Symptom:** No error, but no IRC messages arrive for an extended period.

**Cause:** IRC server timeouts, network blips, stale TCP connections.

**Current handling:** `irc/listener.py` auto-reconnects with backoff. The Rich Live dashboard shows connection state.

### SSE reconnection loop
**Symptom:** Repeated `WARNING:client.pae_sse_client:PaeSseClient disconnected: ... — retrying in 3s`

**Cause:** Orchestrator at `ORCHESTRATOR_BASE_URL` is down or unreachable.

**Current handling:** Reconnects every `SSE_RETRY_DELAY` seconds indefinitely. Does not block IRC processing.

### `.env` changes not picked up without restart
**Symptom:** You change `IRC_NICKNAME` in the config UI but the bot still uses the old name.

**Cause:** Some settings — IRC server, SSE client URL — are read once at startup. Test Run controls (Day/Run/counter) and per-message AI values ARE read live.

**Mitigation:** Restart `pae` after changing startup settings:
```bash
docker-compose restart pae
```

### Schema drift between PAE and orchestrator
**Symptom:** Orchestrator returns `422 Unprocessable Entity`.

**Cause:** Orchestrator schema changed and `pae_schemas.py` is out of sync.

**Examples already handled:**
- `ranking` → `alignmentScore`
- `gbcId` made optional (only included when present)
- `metadata` field added
- `trackId` added to output

**Mitigation:** When the orchestrator team announces a schema update, update `schemas/pae_schemas.py` and the matching `_envelope()` in `agent.py`. The envelope function in `agent.py` is the single source of truth for output shape.

### Docker time drift
**Symptom:** `lastUpdated` timestamps off, breaking time-based queries.

**Fix:** Restart Docker Desktop, or run `wsl --shutdown` on Windows.

### NanoGPT API key expiration
**Symptom:** All NanoGPT calls return 401/403.

**Fix:** Generate a new key, update `AI_API_KEY` in `.env`, restart `pae`.

### Tactical reference CSVs not loaded
**Symptom:** Prompt always shows `(No matching reference terms — use tactical judgment.)`

**Cause:** CSV files missing from `data/`, malformed, or different columns than expected.

**Verify:** Check container logs at startup for `WARNING: CSV not found: ...`.

### Container DNS resolution fails
**Symptom:** PAE can't reach LAN IPs.

**Fix:**
```bash
docker-compose down
docker network prune
docker-compose up
```

### Classify returns `unknown:XXX` callsigns
**Symptom:** `entitiesOfInterest` becomes `["unknown:SECTION4"]`.

**Cause:** Classify API returns provisional tags when it can't resolve a term.

**Mitigation:** The single-entity selector skips `unknown:`-prefixed values when a real callsign or track number is available.

### Request counter overflow on long runs
**Symptom:** Counter shows `0801-100` instead of `0801-00` after 99 requests.

**Mitigation:** Reset via UI between batches, or accept the wider numbers. The format `DDRR-rrr` is still parseable.

### Two PAE instances on the same IRC channel
**Symptom:** Duplicate processing, IRC kicks one for nickname collision.

**Mitigation:** Use unique `IRC_NICKNAME` per environment (e.g. `PAE_Bot_dev`, `PAE_Bot_prod`).

### IRC and SSE process the same event twice
**Symptom:** Two assessments with different IDs but identical content.

**Cause:** Same tactical situation triggers both a chat message AND an SSE retrigger — independent paths.

**Mitigation:** Expected behaviour. If your downstream wants deduplication, do it there.

---

## Operational Checklist

Before each test run:
- [ ] LM Studio is loaded with the configured model (`google/gemma-4-e4b` or `google/gemma-4-31b`)
- [ ] Orchestrator at `ORCHESTRATOR_BASE_URL` responds to a manual GET
- [ ] Track API at `TRACK_API_URL/TN700` returns sample data
- [ ] Classify API at `CLASSIFY_API_URL` accepts a manual POST
- [ ] `RUN_DAY` and `RUN_NUMBER` set correctly in the UI
- [ ] Counter reset via the UI button if continuing a previous run

Mid-run monitoring:
- Watch `pae` terminal for `400 Client Error` patterns indicating AI overload
- Check the Classify tab to verify enrichment is firing
- Check the Dashboard tab to verify assessments are completing
- Check the JSON tab to verify output structure

After the run:
- Save `tactical_output.log` from the container
- Note any 400/422 responses from the orchestrator and report
- Reset the request counter for the next run

---

## Tooling

```bash
# View live logs
docker-compose logs -f pae

# Restart just the PAE service after config changes
docker-compose restart pae

# Hard rebuild (after code changes)
docker-compose down
docker-compose build --no-cache
docker-compose up

# Open a shell in the pae container
docker-compose exec pae sh

# Switch the orchestrator to the local emulator
# In .env or via the UI:
# ORCHESTRATOR_BASE_URL=http://emulator:3016
# GBC_API_URL=http://emulator:3016/paeoutputs
```

---

## Architecture Decisions

A few non-obvious choices worth knowing about:

- **Triage is fail-open.** If the AI is down or slow, every message is treated as relevant. Better to over-process than to silently drop tactical signals.
- **Verb validation happens after AI response.** The model is allowed to produce any verb; we validate against `ALL_VERBS` and replace invalid ones with `NO PAE ACTION REQUIRED`. Faster than constraining generation and catches drift.
- **`entitiesOfInterest` and `battleEntity` are intentionally identical.** The orchestrator schema requires both; the tactical meaning is the same — the subject of the action. Forcing equality removes ambiguity.
- **Single base ID per assessment.** The envelope `id` is `pae-<8 hex>` and each `battleEffect.id` derives from it (`<id>-e01`, `-e02`, `-e03`). Easy to trace effects back to their parent record.
- **Originator is hardcoded to `"rhino"`.** This is the system identity, not the IRC user.
- **`gbcId` and `trackId` are conditionally included.** Only present in JSON when supplied — never `null`. Some orchestrator configs reject null values.
- **Request IDs come from `RUN_DAY`/`RUN_NUMBER` config, not the message.** Earlier versions extracted IDs from message text; that was removed. The counter is always authoritative.
