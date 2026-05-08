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
        callsigns          — identified callsigns from entities_referenced and matched_bins
        track_numbers      — track numbers and JTN IDs from entities_referenced and matched_bins
        entities           — coordinates, mission numbers, contacts, BMA names
        importance_tier    — "HIGH_VALUE", "LOW_VALUE" etc.
        importance_score   — numeric score (1-3)
        confidence         — model confidence (0.0-1.0)
        reasoning          — classifier's reasoning string
    """
    if not classification:
        return {
            "callsigns":       [],
            "track_numbers":   [],
            "entities":        [],
            "importance_tier": "",
            "importance_score": 0,
            "confidence":      0.0,
            "reasoning":       "",
        }

    entities_ref = classification.get("entities_referenced", {})
    matched_bins = classification.get("matched_bins", {})

    # Callsigns — from entities_referenced and matched_bins
    callsigns = list(dict.fromkeys(
        entities_ref.get("callsigns", []) +
        matched_bins.get("callsign", [])
    ))

    # Track numbers — from entities_referenced and matched_bins trackid/jtn
    track_numbers = list(dict.fromkeys(
        entities_ref.get("track_numbers", []) +
        matched_bins.get("trackid", []) +
        matched_bins.get("jtn", [])
    ))

    # All other entities flattened
    entity_fields = ["coordinates", "mission_numbers", "bma_names"]
    entities = []
    for field in entity_fields:
        entities.extend(entities_ref.get(field, []))

    # Add contacts from matched_bins
    entities.extend(matched_bins.get("contact", []))

    # Deduplicate while preserving order
    seen = set()
    unique_entities = []
    for e in entities:
        if e not in seen:
            seen.add(e)
            unique_entities.append(e)

    return {
        "callsigns":        callsigns,
        "track_numbers":    track_numbers,
        "entities":         unique_entities,
        "importance_tier":  classification.get("importance_tier", ""),
        "importance_score": classification.get("importance_score", 0),
        "confidence":       classification.get("confidence", 0.0),
        "reasoning":        classification.get("reasoning", ""),
    }


def fetch_track(track_id: str, api_url: str, timeout: int = 5) -> dict | None:
    """
    Fetch track data from the track API for a given track ID.

    Used exclusively by the SSE path to validate that a retrigger event
    has real track data before committing to a full AI assessment.

    Parameters
    ----------
    track_id  : Track identifier extracted from the SSE event (e.g. "TN700").
    api_url   : Base URL of the track API (e.g. "http://10.5.185.29:3021/tracks").
    timeout   : Request timeout in seconds.

    Returns
    -------
    dict  — track data if the track exists and has content.
    None  — if the track does not exist, returns empty, or any error occurs.
            A None return means the SSE retrigger should be rejected.
    """
    url = f"{api_url.rstrip('/')}/{track_id}"

    try:
        response = requests.get(url, timeout=timeout, headers={"accept": "*/*"})

        if response.status_code == 404:
            print(f"TRACK API: {track_id} not found (404) — rejecting SSE retrigger.")
            return None

        response.raise_for_status()

        # Try to parse as JSON
        try:
            data = response.json()
        except Exception:
            # Non-JSON response — check if body has any content
            if response.text.strip():
                print(f"TRACK API: {track_id} returned non-JSON content.")
                return {"raw": response.text.strip()}
            print(f"TRACK API: {track_id} returned empty body — rejecting SSE retrigger.")
            return None

        # Reject if the response is empty (None, [], {})
        if not data:
            print(f"TRACK API: {track_id} returned empty data — rejecting SSE retrigger.")
            return None

        print(f"TRACK API: {track_id} found — {len(str(data))} bytes of track data.")
        return data

    except requests.exceptions.Timeout:
        print(f"TRACK API: timed out fetching {track_id} — rejecting SSE retrigger.")
        return None
    except requests.exceptions.ConnectionError:
        print(f"TRACK API: cannot reach {api_url} — rejecting SSE retrigger.")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"TRACK API: HTTP error {e} for {track_id} — rejecting SSE retrigger.")
        return None
    except Exception as e:
        print(f"TRACK API: unexpected error ({e}) — rejecting SSE retrigger.")
        return None
