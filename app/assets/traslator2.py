import socket
import uuid
import json
import re
import csv
import requests
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

SERVER      = "10.5.185.72"
PORT        = 6667
CHANNEL     = "#app_dev"
NICKNAME    = f"ABM_Translator_{uuid.uuid4().hex[:4]}"

LM_STUDIO_URL = "http://10.5.185.55:4334/v1/chat/completions"
LM_MODEL      = "google/gemma-4-E4B"
LM_TIMEOUT    = 20  # seconds

# Paths to your CSVs (same folder as this script)
BASE_DIR = Path(__file__).parent
CSV_TACTICAL_CHAT  = BASE_DIR / "standard_tactical_chat_abbreviations.csv"
CSV_BREVITY_CODES  = BASE_DIR / "brevity_codes_2025_standard.csv"
CSV_GLOSSARY       = BASE_DIR / "tactical_glossary_abbreviations.csv"

# ---------------------------------------------------------------------------
# BATTLE DICTIONARY  (verb pool the AI must pick from)
# ---------------------------------------------------------------------------

BATTLE_DICTIONARY = {
    "ATTACK": [
        "ATTACK", "INTERCEPT", "AMBUSH", "ASSAIL", "ASSAULT", "STRIKE", "HIT", "RAID", "INVADE",
        "ADVANCE", "SHOOT", "SUPPRESS", "DISABLE", "SMACK", "DESTROY", "KILL", "NULLIFY", "TERMINATE",
        "VANISH", "RETALIATE", "BRACE FOR IMPACT", "PREPARE", "FORTIFY", "ENGAGE", "COVER",
        "DOUBLE TAP", "CUT OFF", "BANZAI", "TARGET", "HOSTILE", "ENEMY"
    ],
    "INVESTIGATE": [
        "INVESTIGATE", "CONSIDER", "EXAMINE", "EXPLORE", "INSPECT", "INTERROGATE", "PROBE",
        "QUESTION", "REVIEW", "SEARCH", "STUDY", "INQUIRE", "RESEARCH", "FADED", "FADE", "SHADOW",
        "COMMUNICATE", "BROADCAST", "CONTACT", "CONVEY", "CORRESPOND", "DISCLOSE", "REACH OUT",
        "ASLEEP", "AWAKE", "AUTHENTICATE", "PASS ON", "TELL", "TRANSFER", "TRANSMIT", "DISCOVER",
        "RELAY", "REPORT", "RESPOND", "CAPTURE", "IMAGE", "IDENTIFY", "RECOGNIZE", "SPOT", "TRACK",
        "LOCATE", "PINPOINT", "DETECT", "FIND", "UNCOVER", "REVEAL", "EXPOSE", "UNRAVEL", "COLLECT",
        "MONITOR", "SEEN", "WITNESS", "OBSERVE", "WATCH", "VIEW", "PERCEIVE", "LISTEN", "BAD MAP",
        "BEAM RIDER", "CAP", "CAPPING", "CHECK", "DELOUSE", "FEELER", "CATALOG", "ID", "MAP", "MARK",
        "STROKE", "BOLO", "CK", "CHECKMATE", "CONFIRM", "CONFIRMING", "CONFIRMATORY"
    ],
    "DEGRADE": [
        "DEGRADE", "DECEIVE", "DENY", "DELAY", "DIMINISH", "REDUCE", "WEAKEN", "IMPAIR",
        "DETERIORATE", "COUNTER", "HINDER", "COUNTERACT", "OPPOSE", "JAM", "BLOCK", "BIND",
        "CONGEST", "HACK", "HARASS", "HASSLE", "INTIMIDATE", "TORMENT", "DISTURB", "PSYOP",
        "PROPAGANDA", "BUZZER ON"
    ],
    "RESCUE": [
        "RESCUE", "REPAIR", "SAVE", "RECOVER", "RETRIEVE", "FREE", "LIBERATE", "RELEASE",
        "PROTECT", "SHIELD", "EVADE", "AVOID", "CIRCUMVENT", "CONCEAL", "ELUDE", "ESCAPE",
        "FEND OFF", "FLEE", "HIDE", "AVALANCHE", "FLASHLIGHT"
    ]
}

# Flat list for the system prompt (so the model sees every valid choice)
ALL_VERBS = [v for verbs in BATTLE_DICTIONARY.values() for v in verbs]


# ---------------------------------------------------------------------------
# CSV LOADER  — called once at startup
# ---------------------------------------------------------------------------

def load_csv_as_text(filepath: Path) -> str:
    """Read a CSV and return it as a compact pipe-delimited string block."""
    rows = []
    try:
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                rows.append(" | ".join(cell.strip() for cell in row))
        return "\n".join(rows)
    except FileNotFoundError:
        print(f"⚠️  CSV not found: {filepath}")
        return f"[CSV NOT FOUND: {filepath.name}]"


def load_all_csvs() -> str:
    """Combine all three CSVs into one labelled reference block."""
    tc   = load_csv_as_text(CSV_TACTICAL_CHAT)
    brev = load_csv_as_text(CSV_BREVITY_CODES)
    glos = load_csv_as_text(CSV_GLOSSARY)
    return (
        "=== TACTICAL CHAT ABBREVIATIONS ===\n" + tc   + "\n\n"
        "=== BREVITY CODES ===\n"               + brev + "\n\n"
        "=== TACTICAL GLOSSARY ===\n"           + glos
    )


# Load once at import time so every call reuses the same string
CSV_CONTEXT = load_all_csvs()


# ---------------------------------------------------------------------------
# SYSTEM PROMPT
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    verb_list = ", ".join(ALL_VERBS)
    return f"""You are a tactical AI analyst embedded in a real-time battlefield communications pipeline.

Your sole job is to read an incoming tactical chat message and assign exactly THREE effect operator verbs
to the three battle effect slots (e01, e02, e03) in order of tactical priority.

RULES:
1. You MUST choose each verb exclusively from the APPROVED VERB LIST below. No improvisation.
2. Each verb must belong to a DIFFERENT category (ATTACK, INVESTIGATE, DEGRADE, RESCUE) when possible.
   If the message strongly implies only one or two categories, you may repeat a category — but never
   use the exact same verb twice.
3. Rank your choices: e01 = highest priority action, e02 = secondary, e03 = tertiary.
4. Use the three reference tables (Tactical Chat Abbreviations, Brevity Codes, Tactical Glossary)
   to decode any abbreviations or brevity codes in the message before making your decision.
5. Return ONLY valid JSON — no explanation, no markdown, no preamble.

APPROVED VERB LIST:
{verb_list}

OUTPUT FORMAT (strict JSON, nothing else):
{{
  "e01_effectOperator": "<VERB>",
  "e02_effectOperator": "<VERB>",
  "e03_effectOperator": "<VERB>"
}}

REFERENCE TABLES:
{CSV_CONTEXT}
"""


# ---------------------------------------------------------------------------
# IRC FILTER
# ---------------------------------------------------------------------------

def is_clean(text: str) -> bool:
    print(f"DEBUGGING STRING: {repr(text)}")
    clean_text = "".join(re.findall(r'[a-zA-Z0-9\s]', text)).strip()
    parts = clean_text.split()
    if len(parts) < 2:
        return False
    if len(clean_text) < 6:
        return False
    return True


# ---------------------------------------------------------------------------
# LM STUDIO CALL
# ---------------------------------------------------------------------------

def get_verbs_from_lm_studio(msg_content: str) -> tuple[str, str, str]:
    """
    Sends the tactical message to LM Studio running google/gemma-4-E4B.
    Expects back JSON with keys: e01_effectOperator, e02_effectOperator, e03_effectOperator.
    Falls back to PENDING on any failure.
    """
    system_prompt = build_system_prompt()
    user_message  = f"TACTICAL MESSAGE: {msg_content}"

    payload = {
        "model": LM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message}
        ],
        "temperature": 0.2,
        "max_tokens": 120,
        "stream": False
    }

    try:
        response = requests.post(
            LM_STUDIO_URL,
            json=payload,
            timeout=LM_TIMEOUT
        )
        response.raise_for_status()

        data        = response.json()
        raw_content = data["choices"][0]["message"]["content"].strip()

        # Strip markdown code fences if the model wraps its JSON
        raw_content = re.sub(r"^```[a-z]*\n?", "", raw_content)
        raw_content = re.sub(r"\n?```$",        "", raw_content).strip()

        parsed = json.loads(raw_content)

        verb1 = parsed.get("e01_effectOperator", "PENDING").upper()
        verb2 = parsed.get("e02_effectOperator", "PENDING").upper()
        verb3 = parsed.get("e03_effectOperator", "PENDING").upper()

        # Validate — reject anything not in the approved list
        def validate(v):
            return v if v in ALL_VERBS else "PENDING"

        verb1, verb2, verb3 = validate(verb1), validate(verb2), validate(verb3)

        print(f"🤖 AI verbs → e01:[{verb1}]  e02:[{verb2}]  e03:[{verb3}]")
        return verb1, verb2, verb3

    except requests.exceptions.Timeout:
        print(f"⚠️  LM Studio timed out after {LM_TIMEOUT}s — using PENDING.")
    except requests.exceptions.ConnectionError:
        print(f"⚠️  Cannot reach LM Studio at {LM_STUDIO_URL} — using PENDING.")
    except (requests.exceptions.HTTPError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"⚠️  LM Studio error ({type(e).__name__}: {e}) — using PENDING.")

    return "PENDING", "PENDING", "PENDING"


# ---------------------------------------------------------------------------
# JSON BUILDER
# ---------------------------------------------------------------------------

def build_tactical_json(msg_content: str, verb1: str, verb2: str, verb3: str) -> list:
    return [{
        "id": "rhino",
        "requestId": f"track-{uuid.uuid4().hex[:6]}",
        "label": None,
        "description": None,
        "gbcId": None,
        "entitiesOfInterest": [],
        "battleEntity": [],
        "battleEffects": [
            {
                "id": "pae-002-e01",
                "effectOperator": verb1,
                "description": None,
                "timeWindow": None,
                "stateHypothesis": None,
                "opsLimits": [{"description": None, "battleEntity": None, "stateHypothesis": None}],
                "goalContributions": [{"battleGoal": None, "effect": None}],
                "recommended": True,
                "ranking": 1
            },
            {
                "id": "pae-002-e02",
                "effectOperator": verb2,
                "description": None,
                "timeWindow": None,
                "stateHypothesis": None,
                "opsLimits": [{"description": None, "battleEntity": None, "stateHypothesis": None}],
                "goalContributions": [{"battleGoal": None, "effect": None}],
                "recommended": False,
                "ranking": 2
            },
            {
                "id": "pae-002-e03",
                "effectOperator": verb3,
                "description": None,
                "timeWindow": None,
                "stateHypothesis": None,
                "opsLimits": [{"description": None, "battleEntity": None, "stateHypothesis": None}],
                "goalContributions": [{"battleGoal": None, "effect": None}],
                "recommended": False,
                "ranking": 3
            }
        ],
        "chat": [
            msg_content,
            "PAE generated for pre-emptive and defensive options."
        ],
        "isDone": False,
        "originator": "rhino",
        "lastUpdated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
    }]


# ---------------------------------------------------------------------------
# MAIN IRC LOOP
# ---------------------------------------------------------------------------

def start_translator():
    print(f"📚 CSVs loaded — {len(CSV_CONTEXT)} chars of tactical reference ready.")
    print(f"🧠 Model: {LM_MODEL}  →  {LM_STUDIO_URL}")

    try:
        irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        irc.connect((SERVER, PORT))

        irc.send(b"CAP LS 302\r\n")
        irc.send(f"NICK {NICKNAME}\r\n".encode())
        irc.send(f"USER {NICKNAME} 8 * :ABM_JSON_Engine\r\n".encode())

        print(f"--- 📡 TACTICAL FILTER ACTIVE: {CHANNEL} ---")

        while True:
            data = irc.recv(4096).decode("utf-8", errors="ignore")

            for line in data.split("\r\n"):
                if not line:
                    continue

                if line.startswith("PING"):
                    irc.send(f"PONG {line.split()[1]}\r\n".encode())
                    continue

                if " PRIVMSG " in line:
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        msg_content = parts[2]
                        user = parts[1].split("!")[0] if "!" in parts[1] else "Unknown"

                        if is_clean(msg_content):
                            print(f"\n📨 Clean message from {user} — querying LM Studio...")

                            verb1, verb2, verb3 = get_verbs_from_lm_studio(msg_content)
                            tactical_json = build_tactical_json(msg_content, verb1, verb2, verb3)

                            print(f"\n✅ FULL SCHEMA GENERATED FOR: {user}")
                            print(json.dumps(tactical_json, indent=4))

                        else:
                            print(f"🗑️ NOISE FILTERED: '{msg_content}'")

    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")


if __name__ == "__main__":
    start_translator()