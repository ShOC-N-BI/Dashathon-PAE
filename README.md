# PAE — Pre-emptive Action Engine

A tactical AI microservice that listens to J-chat messages from IRC, assesses them using a local LLM, and returns enriched battle JSON to an orchestrator. Also accepts reassessment triggers from the orchestrator cluster via SSE.

---

## What It Does

PAE has two input paths that feed the same AI pipeline:

**Path 1 — IRC (new J-chat messages)**
```
IRC J-chat → filter → AI assessment → POST /paeoutputs to orchestrator
```

**Path 2 — SSE (reassessment requests from the cluster)**
```
Orchestrator SSE event → AI reassessment → POST /paeoutputs to orchestrator
```

For every valid message, the AI assigns three prioritised effect operator verbs (e.g. `STRIKE`, `DETECT`, `JAM`) and populates a full battle JSON record with tactical justifications, time windows, entities of interest, and operational limits.

---

## Project Structure

```
pae/
├── main.py                        # Entry point — wires both input paths
├── config.py                      # All settings loaded from .env
├── .env                           # Your secrets (never commit this)
├── .env.example                   # Template — copy to .env and fill in
│
├── ai/
│   └── agent.py                   # LM Studio AI assessment
│
├── client/
│   ├── http_client.py             # Shared httpx client → orchestrator
│   ├── pae_sse_client.py          # SSE listener (Path 2)
│   └── pae_output_client.py       # POST results back to orchestrator
│
├── irc/
│   └── listener.py                # IRC J-chat listener (Path 1)
│
├── pipeline/
│   ├── filter.py                  # Message noise filter
│   └── builder.py                 # Request ID generator
│
├── schemas/
│   └── pae_schemas.py             # Pydantic models (from DB manager)
│
├── output/
│   └── log_writer.py              # Local backup log
│
├── data/
│   ├── standard_tactical_chat_abbreviations.csv
│   ├── brevity_codes_2025_standard.csv
│   └── tactical_glossary_abbreviations.csv
│
└── tests/
    └── emulator/
        ├── pae_combined_emulator.py   # Fake orchestrator for local testing
        └── pae_run_emulator.py        # Entry point for the emulator
```

---

## Setup

### 1. Install dependencies

```bash
pip install httpx requests psycopg2-binary python-dotenv rich pydantic irc uvicorn fastapi
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
# IRC
IRC_SERVER=10.5.185.72
IRC_PORT=6667
IRC_CHANNEL=#app_dev

# LM Studio (running on your network)
LM_STUDIO_URL=http://10.5.185.55:4334/v1/chat/completions
LM_MODEL=google/gemma-4-e4b
LM_TIMEOUT=20

# Orchestrator
ORCHESTRATOR_BASE_URL=http://10.5.185.XX:PORT
ORCHESTRATOR_API_KEY=your-api-key-here

# SSE
SSE_RETRY_DELAY=5

# Database
DB_HOST=10.5.185.53
DB_NAME=shooca_db
DB_USER=shooca
DB_PASSWORD=your-password
DB_PORT=5432
```

### 3. Run

```bash
python main.py
```

---

## Local Testing (without the real cluster)

The emulator fakes the orchestrator so you can test the full pipeline locally.

**Terminal 1 — start the emulator:**
```bash
python tests/emulator/pae_run_emulator.py
```

**Terminal 2 — update `.env` and start PAE:**
```env
ORCHESTRATOR_BASE_URL=http://127.0.0.1:3016
ORCHESTRATOR_API_KEY=test
```
```bash
python main.py
```

**Fire a reassessment trigger (PowerShell):**
```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:3016/paeinputs" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"requestId":"test-001","trackId":"AMTI SAT detected TBM launch preparations at grid PB1.2","originator":"test-operator"}'
```

**Check the result:**
```
http://127.0.0.1:3016/paeoutputs
http://127.0.0.1:3016/docs      ← Swagger UI
```

---

## AI Models

Two Gemma models are available on the LM Studio host. Switch by changing `LM_MODEL` in `.env`:

| Model | Value | Use |
|---|---|---|
| Gemma 4 E4B | `google/gemma-4-e4b` | Faster, everyday use |
| Gemma 4 31B | `google/gemma-4-31b` | More capable, slower |

---

## Docker

See `docker-compose.yml` to run PAE as a container.

```bash
docker-compose up --build
```

---

## Key Behaviour Notes

- Messages shorter than 2 words or under 6 characters are filtered as noise
- The AI selects three verbs from an approved battle dictionary across four categories: `ATTACK`, `INVESTIGATE`, `DEGRADE`, `RESCUE`
- CSV reference tables (brevity codes, tactical abbreviations) are looked up per-message — only matching rows are sent to the AI to keep the prompt lean
- If the AI returns nothing, the record is marked `NO PAE ACTION REQUIRED`
- All assessments are written to `tactical_output.log` locally regardless of orchestrator availability
