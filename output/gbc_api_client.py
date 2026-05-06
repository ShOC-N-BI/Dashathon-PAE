"""
output/gbc_api_client.py

Posts the full AI battle assessment to the GBC API endpoint.

The GBC API receives the complete battle JSON exactly as the AI produced it.
No fields are stripped or mapped.

Target endpoint: configured via GBC_API_URL in .env
Only runs when GBC_API_URL is set.
"""

import json
import requests


def push(tactical_json: list, api_url: str, timeout: int = 10) -> bool:
    """
    POST the complete battle JSON to the GBC API endpoint as-is.

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

    print(f"GBC API PAYLOAD:\n{json.dumps(record, indent=2)}")

    try:
        response = requests.post(
            api_url,
            json=record,
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
        body = e.response.text if e.response else ""
        print(f"WARNING: GBC API error: {e}  body: {body}")

    return False
