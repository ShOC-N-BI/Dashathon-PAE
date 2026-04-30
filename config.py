from dotenv import load_dotenv
import os

# Load values from .env file at project root
load_dotenv()

# ---------------------------------------------------------------------------
# IRC
# ---------------------------------------------------------------------------
IRC_SERVER  = os.getenv("IRC_SERVER",  "10.5.185.72")
IRC_PORT    = int(os.getenv("IRC_PORT", "6667"))
IRC_CHANNEL = os.getenv("IRC_CHANNEL", "#app_dev")

# ---------------------------------------------------------------------------
# LM Studio
# Host machine on local network running LM Studio at 10.5.185.55:4334
# ---------------------------------------------------------------------------

# Available models — swap LM_MODEL to change which one is used
LM_MODEL_FAST   = "google/gemma-4-e4b"   # smaller, faster responses
LM_MODEL_FULL   = "google/gemma-4-31b"   # larger, more capable

LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://10.5.185.55:4334/v1/chat/completions")
LM_MODEL      = os.getenv("LM_MODEL",      LM_MODEL_FAST)   # change to LM_MODEL_FULL to switch
LM_TIMEOUT    = int(os.getenv("LM_TIMEOUT", "20"))

# ---------------------------------------------------------------------------
# Orchestrator — central hub for the app cluster
# ---------------------------------------------------------------------------
ORCHESTRATOR_BASE_URL = os.getenv("ORCHESTRATOR_BASE_URL", "")  # e.g. http://10.5.185.XX:PORT
ORCHESTRATOR_API_KEY  = os.getenv("ORCHESTRATOR_API_KEY",  "")

# ---------------------------------------------------------------------------
# SSE — retry delay for reconnecting to the orchestrator SSE stream
# ---------------------------------------------------------------------------
SSE_URL         = os.getenv("SSE_URL", "")           # e.g. http://10.5.185.XX:PORT/events
SSE_RETRY_DELAY = int(os.getenv("SSE_RETRY_DELAY", "5"))  # seconds between reconnect attempts

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
