"""
pipeline/triage.py

AI-powered message triage — determines whether an IRC message is tactically
relevant before passing it to the full battle assessment.

This replaces the simple character-count filter with an actual AI judgement.
Fail-open design: if the AI is unreachable, times out, or is uncertain,
the message is treated as relevant and passed through.

Uses TRIAGE_ENDPOINT and TRIAGE_MODEL from .env — can be the same endpoint
as the battle assessment or a separate faster/cheaper model.
"""

import json
import re
import requests


TRIAGE_PROMPT = """You are a tactical message classifier embedded in a military communications pipeline.

Your only job is to decide if an incoming message is tactically relevant.

A message IS relevant if it contains ANY of the following:
- Military units, callsigns, or asset identifiers (e.g. MAYA, VS, RHINO, Alpha-1)
- Coordinates, grid references, or named locations (e.g. PB1.2, Cigar 231/450, grid 441)
- Weapons, threats, or engagement activity (e.g. TBM, SAM, missile, radar, contact)
- Operational orders or status reports (e.g. advance to, hold at, engage, RTB)
- Intelligence or surveillance reports (e.g. detected, observed, confirmed, tracking)
- Any brevity code or tactical abbreviation

A message is NOT relevant if it is:
- Casual conversation or greetings (e.g. hello, how are you, lol)
- IRC system messages or bot output
- Test messages or keyboard noise
- Personal or off-topic chat with no military context

RULES:
- When in doubt, return relevant: true
- Return ONLY valid JSON, no explanation, no markdown

OUTPUT FORMAT:
{"relevant": true}
or
{"relevant": false, "reason": "<one sentence why>"}
"""


def is_relevant(
    message: str,
    triage_url: str,
    triage_model: str,
    api_key: str = "",
    timeout: int = 10,
) -> bool:
    """
    Ask the AI whether a message is tactically relevant.

    Fail-open: returns True (relevant) on any error so messages are never
    silently dropped due to triage failures.

    Parameters
    ----------
    message      : Raw IRC message text to evaluate.
    triage_url   : AI endpoint URL for triage calls.
    triage_model : Model to use for triage (can be faster/cheaper than assessment).
    api_key      : Bearer token — required for NanoGPT, blank for LM Studio.
    timeout      : Request timeout in seconds. Short — triage should be fast.

    Returns
    -------
    True  — message is relevant, pass to assessment.
    False — message is noise, discard.
    """
    payload = {
        "model": triage_model,
        "messages": [
            {"role": "system", "content": TRIAGE_PROMPT},
            {"role": "user",   "content": f"MESSAGE: {message}"},
        ],
        "temperature": 0,
        "stream": False,
    }

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = requests.post(triage_url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()

        raw = response.json()["choices"][0]["message"]["content"].strip()

        # Strip markdown fences if present
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()

        # Extract JSON object
        brace_start = raw.find("{")
        brace_end   = raw.rfind("}")
        if brace_start == -1 or brace_end == -1:
            print(f"TRIAGE: no JSON in response — failing open. raw={repr(raw)}")
            return True

        parsed = json.loads(raw[brace_start : brace_end + 1])
        relevant = parsed.get("relevant", True)
        reason   = parsed.get("reason", "")

        if relevant:
            print(f"TRIAGE: RELEVANT — '{message[:60]}'")
        else:
            print(f"TRIAGE: NOISE — '{message[:60]}' — {reason}")

        return bool(relevant)

    except requests.exceptions.Timeout:
        print(f"TRIAGE: timed out after {timeout}s — failing open.")
        return True
    except requests.exceptions.ConnectionError:
        print(f"TRIAGE: cannot reach {triage_url} — failing open.")
        return True
    except (requests.exceptions.HTTPError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"TRIAGE: error ({type(e).__name__}: {e}) — failing open.")
        return True
