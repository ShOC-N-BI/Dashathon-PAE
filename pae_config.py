from dotenv import load_dotenv, dotenv_values
import os
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"

# Load values from .env file at startup
load_dotenv(ENV_PATH)

# ---------------------------------------------------------------------------
# IRC
# ---------------------------------------------------------------------------
IRC_SERVER  = os.getenv("IRC_SERVER",  "10.5.185.72")
IRC_PORT    = int(os.getenv("IRC_PORT", "6667"))
IRC_CHANNEL = os.getenv("IRC_CHANNEL", "#app_dev")

# ---------------------------------------------------------------------------
# AI Provider — choose which backend handles assessments
# Set AI_PROVIDER to either "lmstudio" or "nanogpt"
# ---------------------------------------------------------------------------
AI_PROVIDER = os.getenv("AI_PROVIDER", "lmstudio")

# ---------------------------------------------------------------------------
# LM Studio — local network LLM server
# ---------------------------------------------------------------------------
LM_MODEL_FAST = "google/gemma-4-e4b"
LM_MODEL_FULL = "google/gemma-4-31b"

LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://10.5.185.55:4334/v1/chat/completions")
LM_MODEL      = os.getenv("LM_MODEL",      LM_MODEL_FAST)
LM_TIMEOUT    = int(os.getenv("LM_TIMEOUT", "60"))  # 60s default — NanoGPT cloud calls need more time

# ---------------------------------------------------------------------------
# NanoGPT — cloud API
# ---------------------------------------------------------------------------
NANOGPT_API_URL = os.getenv("NANOGPT_API_URL", "https://nano-gpt.com/api/v1/chat/completions")
NANOGPT_API_KEY = os.getenv("NANOGPT_API_KEY", "")
NANOGPT_MODEL   = os.getenv("NANOGPT_MODEL",   "gpt-4o")

# ---------------------------------------------------------------------------
# Orchestrator — central hub for the app cluster
# ---------------------------------------------------------------------------
ORCHESTRATOR_BASE_URL = os.getenv("ORCHESTRATOR_BASE_URL", "")
ORCHESTRATOR_API_KEY  = os.getenv("ORCHESTRATOR_API_KEY",  "")

# ---------------------------------------------------------------------------
# SSE
# ---------------------------------------------------------------------------
SSE_URL         = os.getenv("SSE_URL", "")
SSE_RETRY_DELAY = int(os.getenv("SSE_RETRY_DELAY", "5"))

# ---------------------------------------------------------------------------
# Battle API
# ---------------------------------------------------------------------------
BATTLE_API_URL = os.getenv("BATTLE_API_URL", "")

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
# Reads .env fresh from disk — call this before any setting that
# can be changed at runtime via the config UI (port 8080).
# ---------------------------------------------------------------------------

def get_ai_config() -> dict:
    """
    Read AI provider settings directly from .env every time.
    This allows live switching between LM Studio and NanoGPT
    via the config UI without restarting the container.
    """
    # Try multiple possible .env locations (local dev vs Docker container)
    possible_paths = [
        ENV_PATH,
        Path("/app/.env"),
        Path(".env"),
    ]
    values = {}
    for p in possible_paths:
        if p.exists():
            values = dotenv_values(p)
            print(f"CONFIG: loaded .env from {p}  keys={list(values.keys())}")
            break

    # Also check environment variables directly as a fallback
    # (docker-compose env_file injects them into the process environment)
    provider = (values.get("AI_PROVIDER") or os.getenv("AI_PROVIDER") or AI_PROVIDER).strip().lower()
    print(f"CONFIG: AI_PROVIDER resolved to '{provider}'")

    def _get(key, default):
        """Get from .env file first, then process env, then hardcoded default."""
        return values.get(key) or os.getenv(key) or default

    if provider == "nanogpt":
        return {
            "provider": "nanogpt",
            "url":      _get("NANOGPT_API_URL", NANOGPT_API_URL),
            "model":    _get("NANOGPT_MODEL",   NANOGPT_MODEL),
            "api_key":  _get("NANOGPT_API_KEY", NANOGPT_API_KEY),
            "timeout":  int(_get("LM_TIMEOUT",  str(LM_TIMEOUT))),
        }
    else:
        return {
            "provider": "lmstudio",
            "url":      _get("LM_STUDIO_URL", LM_STUDIO_URL),
            "model":    _get("LM_MODEL",      LM_MODEL),
            "api_key":  "",
            "timeout":  int(_get("LM_TIMEOUT", str(LM_TIMEOUT))),
        }
