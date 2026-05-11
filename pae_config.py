from dotenv import load_dotenv, dotenv_values
import os
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"

# Load values from .env file at startup
load_dotenv(ENV_PATH)

# ---------------------------------------------------------------------------
# IRC
# ---------------------------------------------------------------------------
IRC_SERVER   = os.getenv("IRC_SERVER",   "10.5.185.72")
IRC_PORT     = int(os.getenv("IRC_PORT", "6667"))
IRC_CHANNEL  = os.getenv("IRC_CHANNEL",  "#app_dev")
IRC_NICKNAME = os.getenv("IRC_NICKNAME", "")  # leave blank for random name

# ---------------------------------------------------------------------------
# AI — single endpoint, provider auto-detected from URL
# Set AI_ENDPOINT to either LM Studio URL or NanoGPT URL
# ---------------------------------------------------------------------------
AI_ENDPOINT = os.getenv("AI_ENDPOINT", "http://10.5.185.55:4334/v1/chat/completions")
AI_MODEL    = os.getenv("AI_MODEL",    "google/gemma-4-e4b")
AI_API_KEY  = os.getenv("AI_API_KEY",  "")
AI_TIMEOUT  = int(os.getenv("AI_TIMEOUT", "60") or "60")

# ---------------------------------------------------------------------------
# Test Run — controls the DDRR-rr request ID format
# ---------------------------------------------------------------------------
RUN_DAY    = os.getenv("RUN_DAY",    "01")  # DD — day number
RUN_NUMBER = os.getenv("RUN_NUMBER", "01")  # RR — run number within the day

# ---------------------------------------------------------------------------
# Track API — validates SSE retrigger events by fetching track data
# ---------------------------------------------------------------------------
TRACK_API_URL     = os.getenv("TRACK_API_URL", "")   # e.g. http://10.5.185.29:3021/tracks
TRACK_API_TIMEOUT = int(os.getenv("TRACK_API_TIMEOUT", "5") or "5")

# ---------------------------------------------------------------------------
# Classify API — enriches messages with callsigns and entities before assessment
# ---------------------------------------------------------------------------
CLASSIFY_API_URL     = os.getenv("CLASSIFY_API_URL", "")  # e.g. http://10.5.185.30:3060/classify
CLASSIFY_TIMEOUT     = int(os.getenv("CLASSIFY_TIMEOUT", "5") or "5")
IRC_CHANNEL_DEFAULT  = os.getenv("IRC_CHANNEL", "#app_dev").split(",")[0].strip()

# ---------------------------------------------------------------------------
# Triage — fast pre-filter AI call before full assessment
# Can use the same endpoint as AI_ENDPOINT or a separate faster model
# ---------------------------------------------------------------------------
TRIAGE_ENDPOINT = os.getenv("TRIAGE_ENDPOINT", "")  # falls back to AI_ENDPOINT if blank
TRIAGE_MODEL    = os.getenv("TRIAGE_MODEL",    "gpt-4o-mini")
TRIAGE_TIMEOUT  = int(os.getenv("TRIAGE_TIMEOUT", "10") or "10")

# ---------------------------------------------------------------------------
# Orchestrator — central hub for the app cluster
# ---------------------------------------------------------------------------
ORCHESTRATOR_BASE_URL = os.getenv("ORCHESTRATOR_BASE_URL", "")
ORCHESTRATOR_API_KEY  = os.getenv("ORCHESTRATOR_API_KEY",  "")

# ---------------------------------------------------------------------------
# SSE
# ---------------------------------------------------------------------------
SSE_RETRY_DELAY = int(os.getenv("SSE_RETRY_DELAY", "5"))

# ---------------------------------------------------------------------------
# GBC API — external endpoint to push mapped assessment output to
# ---------------------------------------------------------------------------
GBC_API_URL = os.getenv("GBC_API_URL", "")  # e.g. http://10.5.185.29:3016/paeoutputs

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DB_HOST     = os.getenv("DB_HOST",     "10.5.185.53")
DB_NAME     = os.getenv("DB_NAME",     "shooca_db")
DB_USER     = os.getenv("DB_USER",     "shooca")
DB_PASSWORD = os.getenv("DB_PASSWORD", "shooca222")
DB_PORT     = int(os.getenv("DB_PORT", "5432"))


# ---------------------------------------------------------------------------
# LIVE RELOAD
# Reads .env fresh from disk on every call so changes made via the config UI
# take effect on the next message without restarting the container.
# ---------------------------------------------------------------------------

def _detect_provider(url: str) -> str:
    """nano-gpt.com in the URL = nanogpt, anything else = lmstudio."""
    return "nanogpt" if "nano-gpt.com" in url else "lmstudio"


def get_ai_config() -> dict:
    """
    Read AI settings directly from .env every time this is called.
    Provider is automatically detected from the endpoint URL:
      - http://10.5.185.55:4334/...  → lmstudio (no API key needed)
      - https://nano-gpt.com/...     → nanogpt   (API key required)
    """
    # Try multiple possible .env locations
    values = {}
    for p in [ENV_PATH, Path("/app/.env"), Path(".env")]:
        if p.exists():
            values = dotenv_values(p)
            break

    def _get(key, default):
        return values.get(key) or os.getenv(key) or default

    endpoint = _get("AI_ENDPOINT", AI_ENDPOINT)
    model    = _get("AI_MODEL",    AI_MODEL)
    api_key  = _get("AI_API_KEY",  AI_API_KEY)
    timeout  = int(_get("AI_TIMEOUT", str(AI_TIMEOUT)))
    provider = _detect_provider(endpoint)

    # Triage config — fall back to main AI endpoint if TRIAGE_ENDPOINT not set
    triage_url     = _get("TRIAGE_ENDPOINT", TRIAGE_ENDPOINT) or endpoint
    triage_model   = _get("TRIAGE_MODEL",    TRIAGE_MODEL)
    triage_timeout = int(_get("TRIAGE_TIMEOUT", str(TRIAGE_TIMEOUT)))

    print(f"CONFIG: provider={provider.upper()}  endpoint={endpoint}  model={model}  key_set={bool(api_key)}")
    print(f"CONFIG: triage_url={triage_url}  triage_model={triage_model}")

    return {
        "provider":       provider,
        "url":            endpoint,
        "model":          model,
        "api_key":        api_key,
        "timeout":        timeout,
        "triage_url":     triage_url,
        "triage_model":   triage_model,
        "triage_timeout": triage_timeout,
    }
