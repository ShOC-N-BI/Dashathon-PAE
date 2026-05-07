# Integrating with the Shared LM Studio AI Endpoint

This guide is for developers in the cluster who want to connect their own application to the shared LM Studio instance. It covers everything you need to make AI calls, structure prompts, and handle responses — using real working examples from the PAE codebase.

---

## The Shared Endpoint

The LM Studio instance runs on the local network and exposes an OpenAI-compatible API. This means any library or HTTP client that works with OpenAI will work here without modification.

```
Base URL:  http://10.5.185.55:4334
Chat endpoint: http://10.5.185.55:4334/v1/chat/completions
```

**No API key is required for LM Studio.** It accepts requests without authentication.

---

## Available Models

Two models are loaded on the LM Studio host. Set the `model` field in your request to one of these exact strings:

| Model | String | Best for |
|---|---|---|
| Gemma 4 E4B | `google/gemma-4-e4b` | Fast responses, everyday tasks |
| Gemma 4 31B | `google/gemma-4-31b` | Complex reasoning, higher quality |

Start with `google/gemma-4-e4b`. Switch to `google/gemma-4-31b` only if you need better output quality and can accept slower response times.

---

## Making a Request

The endpoint follows the OpenAI chat completions format exactly. Here is the minimal structure:

```json
POST http://10.5.185.55:4334/v1/chat/completions
Content-Type: application/json

{
  "model": "google/gemma-4-e4b",
  "messages": [
    { "role": "system", "content": "Your instructions to the model." },
    { "role": "user",   "content": "The input you want the model to process." }
  ],
  "temperature": 0,
  "stream": false
}
```

The response follows the standard OpenAI format:

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "The model's response text."
      }
    }
  ],
  "usage": {
    "prompt_tokens": 320,
    "completion_tokens": 85,
    "total_tokens": 405
  }
}
```

Your response content is always at:
```python
response["choices"][0]["message"]["content"]
```

---

## Python Example — Basic Call

```python
import requests

def call_ai(system_prompt: str, user_message: str) -> str:
    """
    Send a message to the shared LM Studio instance.
    Returns the model's response as a string.
    """
    response = requests.post(
        "http://10.5.185.55:4334/v1/chat/completions",
        json={
            "model":       "google/gemma-4-e4b",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            "temperature": 0,
            "stream":      False,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


# Usage
result = call_ai(
    system_prompt="You are a helpful assistant. Be concise.",
    user_message="What is the capital of France?"
)
print(result)
```

---

## Getting Structured JSON Back

The most reliable way to use LLMs in production code is to instruct the model to return JSON only — no explanation, no markdown, no preamble. You then parse it yourself.

```python
import requests
import json
import re

def call_ai_json(system_prompt: str, user_message: str) -> dict:
    """
    Call the AI and parse its response as JSON.
    Returns a dict on success, empty dict on failure.
    """
    response = requests.post(
        "http://10.5.185.55:4334/v1/chat/completions",
        json={
            "model":       "google/gemma-4-e4b",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            "temperature": 0,
            "stream":      False,
        },
        timeout=30,
    )
    response.raise_for_status()
    raw = response.json()["choices"][0]["message"]["content"].strip()

    # Strip markdown code fences — some models add them even when told not to
    raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
    raw = re.sub(r"\s*```$",          "", raw).strip()

    # Find the outermost JSON object — handles preamble text before the JSON
    start = raw.find("{")
    end   = raw.rfind("}")
    if start == -1 or end == -1:
        return {}

    return json.loads(raw[start : end + 1])
```

**Why strip code fences?** Models are trained on documentation where JSON is often shown inside ` ```json ... ``` ` blocks. Even when your prompt says "return only JSON", some models add fences out of habit. Stripping them defensively means your code never breaks because of this.

**Why find `{` and `}`?** Models sometimes add a sentence before the JSON like `"Here is the result:"`. Finding the outermost braces extracts just the JSON regardless of what precedes it.

---

## Prompt Design — Getting Reliable Output

The quality and consistency of what you get back depends almost entirely on how you write the system prompt. These patterns work well with the Gemma models:

### Tell the model exactly what it is

```
You are a <role> embedded in a <context>.
Your job is to <specific task>.
```

Being specific about role and context dramatically improves relevance. "You are an assistant" is too vague. "You are a tactical analyst processing military communications" gives the model the framing it needs.

### Define your output format explicitly

Include the exact JSON structure you expect in the prompt:

```
Return ONLY valid JSON in this exact format, nothing else:
{
  "field_one": "<description of what goes here>",
  "field_two": "<description>",
  "field_three": true or false
}
```

### Use rules with numbers

Models follow numbered rules more reliably than prose:

```
RULES:
1. Always return valid JSON. No explanation, no markdown.
2. If you are uncertain, use your best judgment and continue.
3. Never invent field names not listed in the output format.
```

### Give examples of valid and invalid values

```
"status" must be one of: "ACTIVE", "INACTIVE", "PENDING"
Do not use any other values.
```

---

## Setting Temperature

`temperature` controls how random the model's output is.

| Value | Behaviour | Use when |
|---|---|---|
| `0` | Fully deterministic — always picks the most likely token | Structured JSON, classification, consistent formatting |
| `0.2` | Slight variation — mostly consistent | Short creative tasks |
| `0.7` | Moderate variation | Creative writing, brainstorming |
| `1.0` | High variation | Open-ended generation |

**For structured output always use `temperature: 0`.** It is faster, more predictable, and far less likely to produce malformed JSON.

---

## Error Handling

Always wrap AI calls in try/except. The endpoint can be temporarily unavailable, slow to respond, or return an unexpected structure. A robust wrapper:

```python
import requests
import json
import re

LM_STUDIO_URL = "http://10.5.185.55:4334/v1/chat/completions"
DEFAULT_MODEL  = "google/gemma-4-e4b"
TIMEOUT        = 30  # seconds — increase for the 31B model

def ai_call(system_prompt: str, user_message: str, fallback=None):
    """
    Call the shared LM Studio endpoint.

    Returns parsed JSON dict on success.
    Returns fallback value on any failure — never raises.

    Parameters
    ----------
    system_prompt : Instructions for the model.
    user_message  : The input to process.
    fallback      : Value to return on failure. Default is None.
    """
    try:
        response = requests.post(
            LM_STUDIO_URL,
            json={
                "model":       DEFAULT_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
                "temperature": 0,
                "stream":      False,
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()

        raw = response.json()["choices"][0]["message"]["content"].strip()

        # Strip markdown fences
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$",          "", raw).strip()

        # Extract JSON object
        start = raw.find("{")
        end   = raw.rfind("}")
        if start != -1 and end != -1:
            return json.loads(raw[start : end + 1])

        # No JSON found — return raw string as fallback
        return raw if raw else fallback

    except requests.exceptions.Timeout:
        print(f"AI: timed out after {TIMEOUT}s")
        return fallback
    except requests.exceptions.ConnectionError:
        print(f"AI: cannot reach {LM_STUDIO_URL}")
        return fallback
    except requests.exceptions.HTTPError as e:
        print(f"AI: HTTP error {e}")
        return fallback
    except json.JSONDecodeError as e:
        print(f"AI: JSON parse failed — {e}")
        return fallback
    except (KeyError, IndexError) as e:
        print(f"AI: unexpected response structure — {e}")
        return fallback
```

---

## Real Example — Classification

This is how PAE's triage system works. A minimal binary classifier:

```python
CLASSIFIER_PROMPT = """
You are a message classifier. Decide if the message is relevant to military operations.

Return ONLY valid JSON, no explanation:
{"relevant": true}
or
{"relevant": false, "reason": "<one sentence>"}

When in doubt, return relevant: true.
"""

def is_tactically_relevant(message: str) -> bool:
    result = ai_call(
        system_prompt=CLASSIFIER_PROMPT,
        user_message=f"MESSAGE: {message}",
        fallback={"relevant": True},  # fail open
    )
    return bool(result.get("relevant", True))


# Usage
print(is_tactically_relevant("RHINO detected SAM activity at grid PB2.1"))  # True
print(is_tactically_relevant("hey anyone want lunch"))                       # False
```

---

## Real Example — Structured Analysis

This is the pattern PAE uses for battle assessment. Adapt the prompt and output schema to your domain:

```python
ANALYSIS_PROMPT = """
You are an analyst. Read the input and extract structured information.

Return ONLY valid JSON in this exact format, nothing else:
{
  "summary": "<one sentence summary>",
  "entities": ["<entity 1>", "<entity 2>"],
  "priority": "HIGH" or "MEDIUM" or "LOW",
  "action_required": true or false
}
"""

def analyse_message(message: str) -> dict:
    result = ai_call(
        system_prompt=ANALYSIS_PROMPT,
        user_message=message,
        fallback={
            "summary":         "Analysis failed",
            "entities":        [],
            "priority":        "LOW",
            "action_required": False,
        },
    )
    return result


# Usage
result = analyse_message("AMTI SAT confirmed TBM launch preparations at PB1.2")
print(result["priority"])        # HIGH
print(result["action_required"]) # True
print(result["entities"])        # ["AMTI SAT", "TBM", "PB1.2"]
```

---

## Using the OpenAI Python SDK

If you prefer to use the official `openai` Python library rather than raw `requests`, it works with LM Studio directly:

```bash
pip install openai
```

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://10.5.185.55:4334/v1",
    api_key="not-needed",  # LM Studio doesn't require a key — pass anything
)

response = client.chat.completions.create(
    model="google/gemma-4-e4b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user",   "content": "Summarise this in one sentence: ..."},
    ],
    temperature=0,
)

print(response.choices[0].message.content)
```

This is functionally identical to the `requests` approach — use whichever fits your codebase.

---

## Connecting from Docker

If your application runs in Docker, `localhost` and `127.0.0.1` refer to the container itself — not the host machine where LM Studio is running. Use `host.docker.internal` instead:

```
http://host.docker.internal:4334/v1/chat/completions
```

In your `docker-compose.yml` add:
```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

---

## Quick Reference

```python
# Endpoint
URL   = "http://10.5.185.55:4334/v1/chat/completions"

# Models
FAST  = "google/gemma-4-e4b"   # default
FULL  = "google/gemma-4-31b"   # higher quality, slower

# Minimal payload
payload = {
    "model":       FAST,
    "messages":    [
        {"role": "system", "content": "<your instructions>"},
        {"role": "user",   "content": "<your input>"},
    ],
    "temperature": 0,      # always 0 for structured output
    "stream":      False,  # always False unless you need streaming
}

# Response
content = response.json()["choices"][0]["message"]["content"]

# No API key needed for LM Studio
# Add  Authorization: Bearer <key>  only for NanoGPT
```

---

## Tips

- **Start with `temperature: 0`** for any structured output task. Only increase it if you specifically need creative variation.
- **Always define your output format in the prompt.** The more explicit you are, the more consistent the model will be.
- **Implement a fallback.** The model or network can fail. Your code should handle this gracefully and never crash because of an AI call.
- **Keep prompts focused.** One task per call. The model does better when you ask it to do one specific thing well rather than several things at once.
- **Test with short messages first.** The Gemma models perform well on concise prompts. Extremely long system prompts can push smaller models towards degraded output.
- **Use the 31B model for complex reasoning.** If the E4B model produces inconsistent or incomplete JSON, switch to `google/gemma-4-31b` for that specific task.
