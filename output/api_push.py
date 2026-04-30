import json
import requests


def push(tactical_json: list, api_url: str, timeout: int = 10) -> bool:
    """
    POST a tactical JSON record to the Battle API.

    Parameters
    ----------
    tactical_json : The completed battle JSON list produced by pipeline/builder.py.
    api_url       : Full URL of the Battle API endpoint.
    timeout       : Request timeout in seconds.

    Returns
    -------
    True if the push succeeded, False on any failure.
    """
    try:
        response = requests.post(
            api_url,
            json=tactical_json,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        response.raise_for_status()
        print(f"✅  Pushed to Battle API → {response.status_code}")
        return True

    except requests.exceptions.Timeout:
        print(f"⚠️  Battle API timed out after {timeout}s.")
    except requests.exceptions.ConnectionError:
        print(f"⚠️  Cannot reach Battle API at {api_url}.")
    except requests.exceptions.HTTPError as e:
        print(f"⚠️  Battle API returned an error: {e}")

    return False
