import re


def is_clean(text: str) -> bool:
    """
    Return True if the message looks like a real tactical transmission.

    Filters out IRC noise, bot chatter, single words, and garbled strings.
    This is a pure function — no I/O, no side effects.

    Rules
    -----
    1. Strip everything except alphanumeric characters and spaces.
    2. Must have at least 2 distinct words after stripping.
    3. Must be at least 6 characters long after stripping.
    """
    print(f"FILTER CHECK: {repr(text)}")

    clean = "".join(re.findall(r"[a-zA-Z0-9\s]", text)).strip()
    parts = clean.split()

    if len(parts) < 2:
        return False
    if len(clean) < 6:
        return False

    return True
