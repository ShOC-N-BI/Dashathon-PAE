"""
pipeline/enricher.py

Calls the message classification API to get enriched metadata about an IRC
message before passing it to the AI battle assessment.

The classify API returns entity data that the AI doesn't have to infer itself:
- Callsigns identified in the message
- Entities of interest (JTN, track IDs, contacts, coordinates)
- Importance score and tier
- Confidence score

These are extracted and passed to the assessment AI so it can produce a more
accurate and grounded battle JSON record.

Endpoint: configured via CLASSIFY_API_URL in .env
Only enriches if CLASSIFY_API_URL is set — falls back gracefully if not.
"""

import requests


def classify(
    message: str,
    channel: str,
    sender: str,
    timestamp: str,
    api_url: str,
    timeout: int = 5,
) -> dict:
    """
    POST a message to the classify API and return the full response dict.

    Falls back to an empty dict on any failure so the pipeline always continues.

    Parameters
    ----------
    message   : Raw message text.
    channel   : IRC channel the message came from (e.g. "#c2_coord").
    sender    : IRC username of the sender.
    timestamp : Message timestamp string (e.g. "09:08:55").
    api_url   : Full URL of the classify endpoint.
    timeout   : Request timeout in seconds — keep short, this is pre-assessment.

    Returns
    -------
    Full classification response dict, or {} on any failure.
    """
    payload = {
        "channel":   channel,
        "content":   message,
        "sender":    sender,
        "timestamp": timestamp,
    }

    try:
        response = requests.post(
            api_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        print(f"CLASSIFY: tier={data.get('importance_tier', '?')}  "
              f"score={data.get('importance_score', '?')}  "
              f"confidence={data.get('confidence', '?')}")
        return data

    except requests.exceptions.Timeout:
        print(f"CLASSIFY: timed out after {timeout}s — skipping enrichment.")
    except requests.exceptions.ConnectionError:
        print(f"CLASSIFY: cannot reach {api_url} — skipping enrichment.")
    except requests.exceptions.HTTPError as e:
        print(f"CLASSIFY: HTTP error {e} — skipping enrichment.")
    except Exception as e:
        print(f"CLASSIFY: unexpected error ({e}) — skipping enrichment.")

    return {}


def extract_context(classification: dict) -> dict:
    """
    Pull the fields relevant to the AI assessment out of the classify response.

    Returns a dict with:
        callsigns          — list of identified callsigns
        entities           — flat list of all entity values (JTN, track IDs, contacts, coords)
        importance_tier    — "HIGH_VALUE", "LOW_VALUE" etc.
        importance_score   — numeric score (1-3)
        confidence         — model confidence (0.0-1.0)
        reasoning          — classifier's reasoning string
    """
    if not classification:
        return {
            "callsigns":       [],
            "entities":        [],
            "importance_tier": "",
            "importance_score": 0,
            "confidence":      0.0,
            "reasoning":       "",
        }

    entities_ref = classification.get("entities_referenced", {})
    matched_bins = classification.get("matched_bins", {})

    # Callsigns from entities_referenced and matched_bins
    callsigns = list(set(
        entities_ref.get("callsigns", []) +
        matched_bins.get("callsign", [])
    ))

    # All other entity types flattened into one list
    entity_fields = ["track_numbers", "coordinates", "mission_numbers", "bma_names"]
    entities = []
    for field in entity_fields:
        entities.extend(entities_ref.get(field, []))

    # Add JTN and track IDs from matched_bins
    for key in ["jtn", "trackid", "contact"]:
        entities.extend(matched_bins.get(key, []))

    # Deduplicate while preserving order
    seen = set()
    unique_entities = []
    for e in entities:
        if e not in seen:
            seen.add(e)
            unique_entities.append(e)

    return {
        "callsigns":        callsigns,
        "entities":         unique_entities,
        "importance_tier":  classification.get("importance_tier", ""),
        "importance_score": classification.get("importance_score", 0),
        "confidence":       classification.get("confidence", 0.0),
        "reasoning":        classification.get("reasoning", ""),
    }
