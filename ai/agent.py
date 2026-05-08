import csv
import json
import uuid
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
    "SUPPLY": [
        "RESUPPLY", "REARM", "REFUEL", "REFIT", "REPLENISH", "SUSTAIN", "DELIVER", "TRANSPORT",
        "DISTRIBUTE", "STOCKPILE", "CACHE", "PROVISION", "EQUIP", "LOAD", "UNLOAD", "STAGE",
        "FORWARD", "PUSH", "PULL", "REQUISITION", "ALLOCATE", "DISPATCH", "CONVOY", "AIRLIFT",
        "AIRDROP", "OFFLOAD", "PREPOSITION", "CONSOLIDATE", "TRANSFER", "ROTATE",
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

    MAX_ROWS_PER_TABLE = 5
    sections = []
    for label, rows in _ALL_ROWS.items():
        if not rows:
            continue
        header  = rows[0]
        matched = [r for r in rows[1:] if any(t in " ".join(r).upper() for t in terms)]
        if not matched:
            continue
        block = "\n".join(" | ".join(c.strip() for c in r) for r in [header] + matched[:MAX_ROWS_PER_TABLE])
        sections.append(f"=== {label} ===\n{block}")

    return "\n\n".join(sections) if sections else "(No matching reference terms — use tactical judgment.)"


# ---------------------------------------------------------------------------
# SYSTEM PROMPT  — original, unchanged
# ---------------------------------------------------------------------------

def _build_messages(msg: str, enriched: dict = None) -> tuple[str, str]:
    """
    Minimal two-message format for gemma-4-e4b's small context window.
    Verb list is NOT sent — model picks tactical verbs, we validate after.
    """
    context = _get_relevant_context(msg)

<<<<<<< Updated upstream
    # Build enriched block
    enriched_block = ""
    if enriched:
        lines = []
        if enriched.get("callsigns"):     lines.append(f"Callsigns: {', '.join(enriched['callsigns'])}")
        if enriched.get("track_numbers"): lines.append(f"Tracks: {', '.join(enriched['track_numbers'])}")
        if enriched.get("entities"):      lines.append(f"Entities: {', '.join(enriched['entities'])}")
        if enriched.get("importance_tier"): lines.append(f"Tier: {enriched['importance_tier']}")
        if lines:
            enriched_block = "INTEL: " + " | ".join(lines) + "\n"

    system_msg = (
        "You are a tactical AI analyst. "
        "Read the MESSAGE and return ONLY a valid JSON object. "
        "No markdown, no explanation, no extra text."
    )
=======
    enriched_block = ""
    if enriched:
        callsigns     = enriched.get("callsigns", [])
        track_numbers = enriched.get("track_numbers", [])
        entities      = enriched.get("entities", [])
        tier          = enriched.get("importance_tier", "")
        score         = enriched.get("importance_score", 0)
        reasoning     = enriched.get("reasoning", "")

        lines = ["PRE-CLASSIFIED CONTEXT (extracted by message classifier):"]
        if callsigns:     lines.append(f"Callsigns identified: {', '.join(callsigns)}")
        if track_numbers: lines.append(f"Track numbers / JTN IDs: {', '.join(track_numbers)}")
        if entities:      lines.append(f"Entities of interest: {', '.join(entities)}")
        if tier:          lines.append(f"Importance: {tier} (score {score})")
        if reasoning:     lines.append(f"Classifier reasoning: {reasoning}")
        lines.append("Use this context to populate entitiesOfInterest and battleEntity accurately.")
        enriched_block = "\n".join(lines) + "\n"
>>>>>>> Stashed changes

    ref_block = ("REF: " + context + "\n") if context.strip() and "No matching" not in context else ""

    user_msg = f"""Return this JSON filled in for the message below:
{{"label":"<title>","description":"<summary>","entitiesOfInterest":["<entity>"],"battleEntity":["<entity>"],"battleEffects":[
{{"id":"pae-002-e01","effectOperator":"<tactical verb>","description":"<why>","timeWindow":"<0-5m>","stateHypothesis":"<outcome>","opsLimits":[{{"description":"<limit>","battleEntity":"<asset>","stateHypothesis":"<risk>"}}],"goalContributions":[{{"battleGoal":"2.1.c","effect":"high"}}],"recommended":true,"alignmentScore":1.0}},
{{"id":"pae-002-e02","effectOperator":"<tactical verb>","description":"<why>","timeWindow":"<5-15m>","stateHypothesis":"<outcome>","opsLimits":[{{"description":"<limit>","battleEntity":"<asset>","stateHypothesis":"<risk>"}}],"goalContributions":[{{"battleGoal":"2.1.c","effect":"medium"}}],"recommended":false,"alignmentScore":0.6}},
{{"id":"pae-002-e03","effectOperator":"<tactical verb>","description":"<why>","timeWindow":"<15-30m>","stateHypothesis":"<outcome>","opsLimits":[{{"description":"<limit>","battleEntity":"<asset>","stateHypothesis":"<risk>"}}],"goalContributions":[{{"battleGoal":"2.1.c","effect":"low"}}],"recommended":false,"alignmentScore":0.3}}
]}}

Rules: entitiesOfInterest and battleEntity must be the same list. opsLimits battleEntity must not be null.
{enriched_block}{ref_block}MESSAGE: {msg}"""

<<<<<<< Updated upstream
    return system_msg, user_msg
=======
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
      "alignmentScore": 1.0
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
      "alignmentScore": 0.6
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
      "alignmentScore": 0.3
    }}
  ]
}}

REFERENCE TABLES (terms relevant to this message only):
{context}

{enriched_block}"""
>>>>>>> Stashed changes


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
    enriched: dict = None,
    gbc_id: str = None,
) -> list:
<<<<<<< Updated upstream
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
    system_msg, user_msg = _build_messages(msg_content, enriched)
=======
>>>>>>> Stashed changes
    payload = {
        "model": lm_model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        "temperature": 0.1,
        "stream": False,
    }

    raw = ""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")

    def _envelope(ai_fields: dict) -> list:
        # Merge AI entities + enriched into unified lists
        ai_entities = ai_fields.get("entitiesOfInterest", [])
        if not isinstance(ai_entities, list):
            ai_entities = [ai_entities] if ai_entities else []
<<<<<<< Updated upstream
        ai_battle   = ai_fields.get("battleEntity", [])
        if not isinstance(ai_battle, list):
            ai_battle = [ai_battle] if ai_battle else []

        # Merge all sources into one unified list
=======
        ai_battle = ai_fields.get("battleEntity", [])
        if not isinstance(ai_battle, list):
            ai_battle = [ai_battle] if ai_battle else []

>>>>>>> Stashed changes
        extra = []
        if enriched:
            extra = (enriched.get("entities", []) +
                     enriched.get("track_numbers", []) +
                     enriched.get("callsigns", []))

<<<<<<< Updated upstream
        unified = list(dict.fromkeys(ai_entities + ai_battle + extra))

        # entitiesOfInterest and battleEntity are always identical
        merged_entities = unified
        merged_battle   = unified

        return [{
            "id": str(uuid.uuid4()),
            "requestId": request_id,
            **( {"gbcId": gbc_id} if gbc_id else {} ),
            "label": ai_fields.get("label", "Tactical Update"),
            "description": ai_fields.get("description", ""),
            "entitiesOfInterest": merged_entities,
            "battleEntity": merged_battle,
=======
        # entitiesOfInterest and battleEntity are always identical
        unified = list(dict.fromkeys(ai_entities + ai_battle + extra))

        return [{
            "id":          str(uuid.uuid4()),
            "requestId":   request_id,
            **( {"gbcId": gbc_id} if gbc_id else {} ),
            "label":       ai_fields.get("label", "Tactical Update"),
            "description": ai_fields.get("description", ""),
            "entitiesOfInterest": unified,
            "battleEntity":       unified,
>>>>>>> Stashed changes
            "battleEffects": ai_fields.get("battleEffects", []),
            "chat": [msg_content, "PAE generated for pre-emptive and defensive options."],
            "isDone":      False,
            "originator":  "rhino",
            "lastUpdated": now,
<<<<<<< Updated upstream
            "metadata": {},
=======
            "metadata":    {},
>>>>>>> Stashed changes
        }]

    def _effect_stub(eid: str, operator: str, ranking: int, recommended: bool) -> dict:
        score_map = {1: 1.0, 2: 0.6, 3: 0.3}
        return {
            "id":             eid,
            "effectOperator": operator,
            "description":    None,
            "timeWindow":     None,
            "stateHypothesis": None,
            "opsLimits":      [{"description": None, "battleEntity": None, "stateHypothesis": None}],
            "goalContributions": [{"battleGoal": None, "effect": None}],
            "recommended":    recommended,
            "alignmentScore": score_map.get(ranking, 0.3),
        }

    def _error_record(reason: str) -> list:
        return [{
<<<<<<< Updated upstream
            "id": str(uuid.uuid4()),
            "requestId": request_id,
            **( {"gbcId": gbc_id} if gbc_id else {} ),
            "label": "ERROR",
=======
            "id":          str(uuid.uuid4()),
            "requestId":   request_id,
            **( {"gbcId": gbc_id} if gbc_id else {} ),
            "label":       "ERROR",
>>>>>>> Stashed changes
            "description": reason,
            "entitiesOfInterest": [],
            "battleEntity":       [],
            "battleEffects": [
                _effect_stub("pae-002-e01", "ERROR", 1, True),
                _effect_stub("pae-002-e02", "ERROR", 2, False),
                _effect_stub("pae-002-e03", "ERROR", 3, False),
            ],
            "chat":        [msg_content, "PAE generation failed."],
            "isDone":      False,
            "originator":  "rhino",
            "lastUpdated": now,
<<<<<<< Updated upstream
            "metadata": {},
=======
            "metadata":    {},
>>>>>>> Stashed changes
        }]

    def _no_pae_record() -> list:
        return [{
<<<<<<< Updated upstream
            "id": str(uuid.uuid4()),
            "requestId": request_id,
            **( {"gbcId": gbc_id} if gbc_id else {} ),
            "label": "NO PAE ACTION REQUIRED",
=======
            "id":          str(uuid.uuid4()),
            "requestId":   request_id,
            **( {"gbcId": gbc_id} if gbc_id else {} ),
            "label":       "NO PAE ACTION REQUIRED",
>>>>>>> Stashed changes
            "description": "Message assessed — no pre-emptive or defensive action warranted.",
            "entitiesOfInterest": [],
            "battleEntity":       [],
            "battleEffects": [
                _effect_stub("pae-002-e01", "NO PAE ACTION REQUIRED", 1, True),
                _effect_stub("pae-002-e02", "NO PAE ACTION REQUIRED", 2, False),
                _effect_stub("pae-002-e03", "NO PAE ACTION REQUIRED", 3, False),
            ],
            "chat":        [msg_content, "PAE generated for pre-emptive and defensive options."],
            "isDone":      False,
            "originator":  "rhino",
            "lastUpdated": now,
<<<<<<< Updated upstream
            "metadata": {},
        }]

    def _effect_stub(eid: str, operator: str, ranking: int, recommended: bool) -> dict:
        score_map = {1: 1.0, 2: 0.6, 3: 0.3}
        return {
            "id": eid,
            "effectOperator": operator,
            "description": None,
            "timeWindow": None,
            "stateHypothesis": None,
            "opsLimits": [{"description": None, "battleEntity": None, "stateHypothesis": None}],
            "goalContributions": [{"battleGoal": None, "effect": None}],
            "recommended": recommended,
            "alignmentScore": score_map.get(ranking, 0.3),
        }

=======
            "metadata":    {},
        }]

>>>>>>> Stashed changes
    try:
        headers = {"Content-Type": "application/json"}
        if provider == "nanogpt" and api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        print(f"AI PROVIDER: {provider.upper()}  MODEL: {payload['model']}")
        response = requests.post(lm_url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()

        full_response = response.json()
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

        parsed = json.loads(raw[brace_start : brace_end + 1])

        # Validate effectOperator verbs
        effects = parsed.get("battleEffects", [])
        for effect in effects:
            v = effect.get("effectOperator", "").upper().strip()
            effect["effectOperator"] = v if v in ALL_VERBS else "NO PAE ACTION REQUIRED"

            # Ensure opsLimits is fully populated
            ops = effect.get("opsLimits", [])
            if not ops:
                effect["opsLimits"] = [{
                    "description":     "No specific operational constraint identified.",
                    "battleEntity":    "Unspecified",
                    "stateHypothesis": "Outcome dependent on available assets.",
                }]
            else:
                for op in ops:
                    if not op.get("battleEntity"):    op["battleEntity"]    = "Unspecified"
                    if not op.get("description"):     op["description"]     = "No specific operational constraint identified."
                    if not op.get("stateHypothesis"): op["stateHypothesis"] = "Outcome dependent on available assets."

        raw_verbs = [e.get("effectOperator", "?") for e in effects[:3]]
        print(f"AI raw verbs: {raw_verbs}")
        print(f"AI assessment complete — label: {parsed.get('label', '?')}")
        return _envelope(parsed)

    except requests.exceptions.Timeout:
        print(f"WARNING: AI provider timed out after {timeout}s ({lm_url}).")
        return _error_record(f"AI provider timed out after {timeout}s.")
    except requests.exceptions.ConnectionError:
        print(f"WARNING: Cannot reach AI provider at {lm_url}.")
        return _error_record(f"Cannot reach AI provider at {lm_url}.")
    except requests.exceptions.HTTPError as e:
<<<<<<< Updated upstream
        # Print the full response body so we can see exactly what LM Studio rejected
=======
>>>>>>> Stashed changes
        body = ""
        try:
            body = e.response.text if e.response else ""
        except Exception:
            pass
        print(f"WARNING: AI provider HTTP error: {e}.")
        print(f"WARNING: LM Studio response body: {body}")
<<<<<<< Updated upstream
        print(f"WARNING: Payload sent:\n{json.dumps(payload, indent=2)[:2000]}")
=======
>>>>>>> Stashed changes
        return _error_record(f"HTTP error: {e}.")
    except (ValueError, KeyError) as e:
        print(f"WARNING: Unexpected response structure ({type(e).__name__}: {e}).")
        return _error_record(f"Unexpected response structure: {e}.")
    except json.JSONDecodeError as e:
        print(f"WARNING: JSON parse failed: {e} — raw was: {repr(raw)}.")
        return _error_record(f"JSON parse failed: {e}.")