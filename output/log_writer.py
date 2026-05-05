import json
from pathlib import Path

# Default log location — can be overridden by passing a path
DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent / "tactical_output.log"


def write(tactical_json: list, log_path: Path = DEFAULT_LOG_PATH) -> None:
    """
    Append a tactical JSON record to the log file.
    Each record is written as a single line of JSON.

    Parameters
    ----------
    tactical_json : The completed battle JSON list produced by pipeline/builder.py.
    log_path      : Path to the log file. Defaults to tactical_output.log at project root.
    """
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(tactical_json) + "\n")
        print(f"📝  Logged to {log_path.name}")
    except OSError as e:
        print(f"⚠️  Log write failed: {e}")
