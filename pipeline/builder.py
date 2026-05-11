"""
pipeline/builder.py

Generates request IDs in the format DDRR-rr where:
    DD = Day number (e.g. 01)
    RR = Run number (e.g. 01)
    rr = Request number for this run (auto-increments, resets on run change)

Example: Day 01, Run 02, Request 05 → 0102-05

Day and Run are read live from .env on every call so they can be updated
from the config UI without restarting the container.
The request counter auto-increments in memory and resets when RUN_NUMBER changes.
"""

import threading
from dotenv import dotenv_values
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# ---------------------------------------------------------------------------
# In-memory counter — resets when RUN_NUMBER changes
# ---------------------------------------------------------------------------
_lock           = threading.Lock()
_request_count  = 0
_last_run_key   = None   # tracks last seen DD+RR so we know when to reset


def _read_run_config() -> tuple[str, str]:
    """Read RUN_DAY and RUN_NUMBER fresh from .env."""
    try:
        for p in [ENV_PATH, Path("/app/.env"), Path(".env")]:
            if p.exists():
                v = dotenv_values(p)
                day = str(v.get("RUN_DAY",    "01")).zfill(2)
                run = str(v.get("RUN_NUMBER", "01")).zfill(2)
                return day, run
    except Exception:
        pass
    return "01", "01"


def make_request_id() -> str:
    """
    Generate the next request ID in DDRR-rr format.

    Reads RUN_DAY and RUN_NUMBER fresh from .env on every call so changes
    made in the config UI take effect immediately. The request counter resets
    to 01 automatically whenever Day or Run changes.

    Returns e.g. "0101-01", "0102-05", "0203-12"
    """
    global _request_count, _last_run_key

    day, run = _read_run_config()
    run_key  = f"{day}{run}"

    with _lock:
        if run_key != _last_run_key:
            # Day or Run changed — reset counter
            _request_count = 0
            _last_run_key  = run_key

        _request_count += 1
        count = _request_count

    return f"{day}{run}-{str(count).zfill(2)}"


def reset_counter() -> None:
    """Reset the request counter to 0. Called from the config server reset button."""
    global _request_count
    with _lock:
        _request_count = 0
    print("REQUEST COUNTER: reset to 0")


def current_state() -> dict:
    """Return current day, run, and request count for the config UI status panel."""
    day, run = _read_run_config()
    return {
        "day":     day,
        "run":     run,
        "count":   _request_count,
        "next_id": f"{day}{run}-{str(_request_count + 1).zfill(2)}",
    }



def extract_track_id(message: str) -> str | None:
    """
    Extract a track ID from a message string.
    Matches 2-letter prefix followed by digits (TN700, TS016, TL005, TT024 etc.)
    Returns the FIRST track ID found, uppercased, or None if none present.
    """
    import re
    # Look for word-boundary 2-letter + digits patterns
    match = re.search(r"\b([A-Za-z]{2}\d+)\b", message)
    return match.group(1).upper() if match else None


def extract_request_id(message: str) -> str | None:
    """
    Extract a DDRR-rr format request ID from an IRC message.

    Looks for a pattern of 4 digits, a dash, and 2 digits (e.g. 0602-02).
    Returns the first match found, or None if the message has no embedded ID.

    Examples:
        "gen bcoa using rainmaker jtn tn044 0602-02 B pls" → "0602-02"
        "@vegas_pit_a bcoa options ... 0802-01 pls"        → "0802-01"
        "TBM launch detected at PB1.2"                     → None
    """
    import re
    match = re.search(r"\b(\d{4}-\d{2})\b", message)
    return match.group(1) if match else None
