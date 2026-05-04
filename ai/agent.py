import csv
import json
import re
import requests
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# PATHS  — CSVs live in data/ at the project root
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_TACTICAL_CHAT = BASE_DIR / "data" / "standard_tactical_chat_abbreviations.csv"
CSV_BREVITY_CODES = BASE_DIR / "data" / "brevity_codes_2025_standard.csv"
CSV_GLOSSARY      = BASE_DIR / "data" / "tactical_glossary_abbreviations.csv"

# ---------------------------------------------------------------------------
# BATTLE DICTIONARY  — verb pool the AI must pick from
# ---------------------------------------------------------------------------

BATTLE_DICTIONARY = {
    "ATTACK": [
        "ATTACK", "INTERCEPT", "AMBUSH", "ASSAIL", "ASSAULT", "STRIKE", "HIT", "RAID", "INVADE",
        "ADVANCE", "SHOOT", "SUPPRESS", "DISABLE", "SMACK", "DESTROY", "KILL", "NULLIFY", "TERMINATE",
        "VANISH", "RETALIATE", "BRACE FOR IMPACT", "PREPARE", "FORTIFY", "ENGAGE", "COVER",
        "DOUBLE TAP", "CUT OFF", "BANZAI", "TARGET", "HOSTILE", "ENEMY",
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
        "STROKE", "BOLO", "CK", "CHECKMATE", "CONFIRM", "CONFIRMING", "CONFIRMATORY",
    ],
    "DEGRADE": [
        "DEGRADE", "DECEIVE", "DENY", "DELAY", "DIMINISH", "REDUCE", "WEAKEN", "IMPAIR",
        "DETERIORATE", "COUNTER", "HINDER", "COUNTERACT", "OPPOSE", "JAM", "BLOCK", "BIND",
        "CONGEST", "HACK", "HARASS", "HASSLE", "INTIMIDATE", "TORMENT", "DISTURB", "PSYOP",
        "PROPAGANDA", "BUZZER ON",
    ],
    "RESCUE": [
        "RESCUE", "REPAIR", "SAVE", "RECOVER", "RETRIEVE", "FREE", "LIBERATE", "RELEASE",
        "PROTECT", "SHIELD", "EVADE", "AVOID", "CIRCUMVENT", "CONCEAL", "ELUDE", "ESCAPE",
        "FEND OFF", "FLEE", "HIDE", "AVALANCHE", "FLASHLIGHT",
    ],
}

ALL_VERBS: list[str] = [v for verbs in BATTLE_DICTIONARY.values() for v in verbs]

# ---------------------------------------------------------------------------
# TARGETED CSV LOOKUP
# ---------------------------------------------------------------------------

def _load_csv_rows(filepath: Path) -> list[list[str]]:
    try:
        with open(filepath, newline="", encoding="utf-8") as f:
            return list(csv.reader(f))
    except FileNotFoundError:
        print(f"WARNING: CSV not found: {filepath}")
        return []

_ALL_ROWS = {
    "TACTICAL CHAT ABBREVIATIONS": _load_csv_rows(CSV_TACTICAL_CHAT),
    "BREVITY CODES":               _load_csv_rows(CSV_BREVITY_CODES),
    "TACTICAL GLOSSARY":           _load_csv_rows(CSV_GLOSSARY),
}


def _get_relevant_context(msg: str) -> str:
    words = msg.upper().split()
    terms = set(words)
    terms.update(f"{words[i]} {words[i+1]}" for i in range(len(words) - 1))

    sections = []
    for label, rows in _ALL_ROWS.items():
        if not rows:
            continue
        header  = rows[0]
        matched = [r for r in rows[1:] if any(t in " ".join(r).upper() for t in terms)]
        if not matched:
            continue
        block = "\n".join(" | ".join(c.strip() for c in r) for r in [header] + matched)
        sections.append(f"=== {label} ===\n{block}")

    return "\n\n".join(sections) if sections else "(No matching reference terms — use tactical judgment.)"


# ---------------------------------------------------------------------------
# SYSTEM PROMPT
# ---------------------------------------------------------------------------

def _build_system_prompt(msg: str) -> str:
    verb_list = ", ".join(ALL_VERBS)
    context   = _get_relevant_context(msg)

    return f"""You are a tactical AI analyst embedded in a real-time battlefield communications pipeline.

Your job is to analyse an incoming tactical message and return a SINGLE fully populated battle JSON object.

RULES:
1. effectOperator values MUST come exclusively from the APPROVED VERB LIST. No other words.
2. Use a DIFFERENT category (ATTACK / INVESTIGATE / DEGRADE / RESCUE) for each effect slot where possible.
   Never use the exact same verb twice.
3. e01 = highest priority (recommended: true), e02 = secondary, e03 = tertiary.
4. All descriptive fields must be concise and tactically relevant to the message.
5. entitiesOfInterest: key locations, coordinates, or named systems found in the message.
6. battleEntity: the vehicle or actor types involved (e.g. "TBM", "SAT", "F-16").
7. timeWindow: your best estimate of urgency (e.g. "0-5m", "5-15m", "15-30m").
8. stateHypothesis: the tactical outcome if this effect is enacted.
9. opsLimits MUST always include ALL THREE fields: "description", "battleEntity", and "stateHypothesis".
   "battleEntity" inside opsLimits is the specific vehicle or asset required for that effect (e.g. "EA-18G", "F-16", "Analyst").
   NEVER omit "battleEntity" from opsLimits. It is a required field.
10. Return ONLY valid JSON — no explanation, no markdown, no preamble.

APPROVED VERB LIST:
{verb_list}

OUTPUT FORMAT (strict JSON, nothing else):
{{
  "label": "<short tactical title>",
  "description": "<brief strategic summary of message intent>",
  "entitiesOfInterest": ["<key term or location>"],
  "battleEntity": ["<vehicle or actor type>"],
  "battleEffects": [
    {{
      "id": "pae-002-e01",
      "effectOperator": "<VERB from approved list>",
      "description": "<justification for this action>",
      "timeWindow": "<urgency estimate>",
      "stateHypothesis": "<tactical outcome if enacted>",
      "opsLimits": [{{
        "description": "<operational constraint>",
        "battleEntity": "<vehicle required for this effect>",
        "stateHypothesis": "<variables or risks>"
      }}],
      "goalContributions": [{{"battleGoal": "2.1.c", "effect": "high"}}],
      "recommended": true,
      "ranking": 1
    }},
    {{
      "id": "pae-002-e02",
      "effectOperator": "<VERB from approved list>",
      "description": "<justification for secondary choice>",
      "timeWindow": "<urgency estimate>",
      "stateHypothesis": "<tactical outcome>",
      "opsLimits": [{{
        "description": "<operational constraint>",
        "battleEntity": "<vehicle required>",
        "stateHypothesis": "<variables or risks>"
      }}],
      "goalContributions": [{{"battleGoal": "2.1.c", "effect": "medium"}}],
      "recommended": false,
      "ranking": 2
    }},
    {{
      "id": "pae-002-e03",
      "effectOperator": "<VERB from approved list>",
      "description": "<justification for tertiary choice>",
      "timeWindow": "<urgency estimate>",
      "stateHypothesis": "<tactical outcome>",
      "opsLimits": [{{
        "description": "<operational constraint>",
        "battleEntity": "<vehicle required>",
        "stateHypothesis": "<variables or risks>"
      }}],
      "goalContributions": [{{"battleGoal": "2.1.c", "effect": "low"}}],
      "recommended": false,
      "ranking": 3
    }}
  ]
}}

REFERENCE TABLES (terms relevant to this message only):
{context}
"""


# ---------------------------------------------------------------------------
# PUBLIC INTERFACE
# ---------------------------------------------------------------------------

def get_battle_assessment(
    msg_content: str,
    username: str,
    request_id: str,
    lm_url: str,
    lm_model: str,
    timeout: int = 20,
    provider: str = "lmstudio",
    api_key: str = "",
) -> list:
    """
    Send a tactical message to the configured AI provider and return a fully
    populated battle JSON list.

    Parameters
    ----------
    provider : "lmstudio" or "nanogpt"
    api_key  : Required for NanoGPT. Leave blank for LM Studio.

    Returns
    -------
    A list containing one battle JSON dict ready for output.
    Falls back to a minimal error record on failure.
    """
    payload = {
        "model": lm_model,
        "messages": [
            {"role": "system", "content": _build_system_prompt(msg_content)},
            {"role": "user",   "content": f"TACTICAL MESSAGE: {msg_content}"},
        ],
        "temperature": 0.2,
        "stream": False,
    }

    raw = ""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")

    def _envelope(ai_fields: dict) -> list:
        """Wrap AI-generated fields in the full battle JSON envelope."""
        return [{
            "id": username,
            "requestId": request_id,
            "label": ai_fields.get("label", "Tactical Update"),
            "description": ai_fields.get("description", ""),
            "gbcId": None,
            "entitiesOfInterest": ai_fields.get("entitiesOfInterest", []),
            "battleEntity": ai_fields.get("battleEntity", []),
            "battleEffects": ai_fields.get("battleEffects", []),
            "chat": [
                msg_content,
                "PAE generated for pre-emptive and defensive options.",
            ],
            "isDone": False,
            "originator": username,
            "lastUpdated": now,
        }]

    def _error_record(reason: str) -> list:
        """Return a minimal record when the AI call fails entirely."""
        return [{
            "id": username,
            "requestId": request_id,
            "label": "ERROR",
            "description": reason,
            "gbcId": None,
            "entitiesOfInterest": [],
            "battleEntity": [],
            "battleEffects": [
                _effect_stub("pae-002-e01", "ERROR", 1, True),
                _effect_stub("pae-002-e02", "ERROR", 2, False),
                _effect_stub("pae-002-e03", "ERROR", 3, False),
            ],
            "chat": [msg_content, "PAE generation failed."],
            "isDone": False,
            "originator": username,
            "lastUpdated": now,
        }]

    def _no_pae_record() -> list:
        """Return a minimal record when the AI determines no action is required."""
        return [{
            "id": username,
            "requestId": request_id,
            "label": "NO PAE ACTION REQUIRED",
            "description": "Message assessed — no pre-emptive or defensive action warranted.",
            "gbcId": None,
            "entitiesOfInterest": [],
            "battleEntity": [],
            "battleEffects": [
                _effect_stub("pae-002-e01", "NO PAE ACTION REQUIRED", 1, True),
                _effect_stub("pae-002-e02", "NO PAE ACTION REQUIRED", 2, False),
                _effect_stub("pae-002-e03", "NO PAE ACTION REQUIRED", 3, False),
            ],
            "chat": [msg_content, "PAE generated for pre-emptive and defensive options."],
            "isDone": False,
            "originator": username,
            "lastUpdated": now,
        }]

    def _effect_stub(eid: str, operator: str, ranking: int, recommended: bool) -> dict:
        return {
            "id": eid,
            "effectOperator": operator,
            "description": None,
            "timeWindow": None,
            "stateHypothesis": None,
            "opsLimits": [{"description": None, "battleEntity": None, "stateHypothesis": None}],
            "goalContributions": [{"battleGoal": None, "effect": None}],
            "recommended": recommended,
            "ranking": ranking,
        }

    try:
        headers = {"Content-Type": "application/json"}
        if provider == "nanogpt" and api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        print(f"AI PROVIDER: {provider.upper()}  MODEL: {payload['model']}")
        response = requests.post(lm_url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()

        full_response = response.json()
        print(f"RAW API RESPONSE:\n{json.dumps(full_response, indent=2)}")

        raw = full_response["choices"][0]["message"]["content"].strip()
        print(f"RAW CONTENT: {repr(raw)}")

        if not raw:
            print("INFO: Model returned empty content — NO PAE ACTION REQUIRED.")
            return _no_pae_record()

        # Strip markdown code fences
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()

        # Extract the JSON object
        brace_start = raw.find("{")
        brace_end   = raw.rfind("}")
        if brace_start == -1 or brace_end == -1:
            print("INFO: No JSON in model output — NO PAE ACTION REQUIRED.")
            return _no_pae_record()

        raw = raw[brace_start : brace_end + 1]
        print(f"EXTRACTED JSON: {repr(raw)}")

        parsed = json.loads(raw)

        # Validate effectOperator verbs and ensure opsLimits are fully populated
        effects = parsed.get("battleEffects", [])
        for effect in effects:
            # Validate verb
            v = effect.get("effectOperator", "").upper().strip()
            effect["effectOperator"] = v if v in ALL_VERBS else "NO PAE ACTION REQUIRED"

            # Ensure opsLimits exists and every entry has the required battleEntity field
            ops = effect.get("opsLimits", [])
            if not ops:
                effect["opsLimits"] = [{
                    "description": "No specific operational constraint identified.",
                    "battleEntity": "Unspecified",
                    "stateHypothesis": "Outcome dependent on available assets.",
                }]
            else:
                for op in ops:
                    if not op.get("battleEntity"):
                        op["battleEntity"] = "Unspecified"
                    if not op.get("description"):
                        op["description"] = "No specific operational constraint identified."
                    if not op.get("stateHypothesis"):
                        op["stateHypothesis"] = "Outcome dependent on available assets."

        print(f"AI assessment complete — label: {parsed.get('label', '?')}")
        return _envelope(parsed)

    except requests.exceptions.Timeout:
        print(f"WARNING: AI provider timed out after {timeout}s ({lm_url}).")
        return _error_record(f"AI provider timed out after {timeout}s.")
    except requests.exceptions.ConnectionError:
        print(f"WARNING: Cannot reach AI provider at {lm_url}.")
        return _error_record(f"Cannot reach AI provider at {lm_url}.")
    except requests.exceptions.HTTPError as e:
        print(f"WARNING: AI provider HTTP error: {e}.")
        return _error_record(f"HTTP error: {e}.")
    except (ValueError, KeyError) as e:
        print(f"WARNING: Unexpected response structure ({type(e).__name__}: {e}).")
        return _error_record(f"Unexpected response structure: {e}.")
    except json.JSONDecodeError as e:
        print(f"WARNING: JSON parse failed: {e} — raw was: {repr(raw)}.")
        return _error_record(f"JSON parse failed: {e}.")
