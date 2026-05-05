"""
output/gbc_api_client.py

Maps the PAE battle JSON to the GBC API schema and POSTs it.

Target endpoint: http://10.5.185.29:3016/paeoutputs  (or as configured)
Swagger:         http://10.5.185.29:3016/swagger

Only runs when GBC_API_URL is configured in .env.
"""

import json
import uuid
import requests
from datetime import datetime, timezone


def _map_to_gbc_schema(record: dict) -> dict:
    """
    Map a PAE battle JSON record to the GBC API output schema.

    Fields that have no equivalent in the battle JSON (latitude, longitude,
    eventType, alertType) are defaulted — confirm values with your API team.
    """
    effects = record.get("battleEffects", [])
    chat    = record.get("chat", [])
    now     = datetime.now(timezone.utc).isoformat()

    # ── eventDetails — only the original message, not the PAE system note ──
    event_details = []
    original_msg = chat[0] if chat else ""
    if original_msg:
        event_details.append({
            "id":          str(uuid.uuid4()),
            "title":       "",
            "time":        record.get("lastUpdated", now),
            "information": original_msg,
            "type":        0,
        })

    # ── targets — one target per battle effect ────────────────────────────
    targets = []
    for effect in effects:
        ops_limits = effect.get("opsLimits", [])
        has_constraint = any(
            op.get("description") or op.get("battleEntity")
            for op in ops_limits
        )

        targets.append({
            "id":      effect.get("id", str(uuid.uuid4())),
            "label":   effect.get("effectOperator", "UNKNOWN"),
            "trackId": record.get("requestId", ""),
            "actions": [
                {
                    "id":                       f"{effect.get('id', 'act')}-action",
                    "verb":                     effect.get("effectOperator", ""),
                    "timingInfo":               effect.get("timeWindow") or "",
                    "justification":            effect.get("description") or "",
                    "hasOperationalConstraint": has_constraint,
                }
            ],
        })

    return {
        "id":           record.get("requestId", str(uuid.uuid4())),
        "label":        record.get("label", "Tactical Update"),
        "status":       "ARCHIVED" if record.get("isDone") else "ACTIVE",
        "priority":     effects[0].get("recommended", True) if effects else True,
        "lastUpdate":   record.get("lastUpdated", now),
        "mission":      record.get("description", ""),
        "latitude":     0.0,   # not in PAE data — update if your messages contain coords
        "longitude":    0.0,   # not in PAE data — update if your messages contain coords
        "eventType":    0,     # confirm with API team
        "alertType":    0,     # confirm with API team
        "canRequestCoas": True,
        "eventDetails": event_details,
        "targets":      targets,
        "isArchived":   record.get("isDone", False),
    }


def push(tactical_json: list, api_url: str, timeout: int = 10) -> bool:
    """
    Map a PAE battle JSON record to the GBC schema and POST it to the API.

    Parameters
    ----------
    tactical_json : The completed battle JSON list from ai.agent.
    api_url       : Full URL of the GBC API endpoint.
    timeout       : Request timeout in seconds.

    Returns
    -------
    True on success, False on any failure.
    """
    record = tactical_json[0] if isinstance(tactical_json, list) else tactical_json

    gbc_payload = _map_to_gbc_schema(record)

    print(f"GBC API PAYLOAD:\n{json.dumps(gbc_payload, indent=2)}")

    try:
        response = requests.post(
            api_url,
            json=gbc_payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        response.raise_for_status()
        print(f"GBC API push OK → {response.status_code}")
        return True

    except requests.exceptions.Timeout:
        print(f"WARNING: GBC API timed out after {timeout}s.")
    except requests.exceptions.ConnectionError:
        print(f"WARNING: Cannot reach GBC API at {api_url}.")
    except requests.exceptions.HTTPError as e:
        print(f"WARNING: GBC API error: {e}  body: {e.response.text if e.response else ''}")

    return False
