import time
import requests
from typing import Callable


def start(
    url: str,
    on_message: Callable[[str, str], None],
    source_label: str = "SSE",
    retry_delay: int = 5,
) -> None:
    """
    Connect to an SSE HTTP stream and listen for events indefinitely.

    For every data event that arrives, calls:
        on_message(source_label, message_text)

    This uses the same callback signature as irc.listener so handle_message
    in main.py works identically for both sources.

    SSE events follow the format:
        data: <message text>
        (blank line to signal end of event)

    Parameters
    ----------
    url          : Full HTTP URL of the SSE endpoint.
    on_message   : Callback that receives (source: str, message: str).
    source_label : Label passed as the "username" to on_message (default "SSE").
    retry_delay  : Seconds to wait before reconnecting on connection loss.
    """
    print(f"📡  SSE listener connecting → {url}")

    while True:
        try:
            with requests.get(url, stream=True, timeout=None, headers={"Accept": "text/event-stream"}) as response:
                response.raise_for_status()
                print(f"✅  SSE stream connected → {url}")

                buffer = []

                for raw_line in response.iter_lines(decode_unicode=True):
                    # A blank line signals the end of one SSE event
                    if raw_line == "" or raw_line is None:
                        if buffer:
                            _dispatch(buffer, source_label, on_message)
                            buffer = []
                        continue

                    buffer.append(raw_line)

        except requests.exceptions.ConnectionError:
            print(f"⚠️  SSE connection lost — retrying in {retry_delay}s...")
        except requests.exceptions.HTTPError as e:
            print(f"⚠️  SSE HTTP error: {e} — retrying in {retry_delay}s...")
        except Exception as e:
            print(f"⚠️  SSE unexpected error: {e} — retrying in {retry_delay}s...")

        time.sleep(retry_delay)


def _dispatch(
    buffer: list[str],
    source_label: str,
    on_message: Callable[[str, str], None],
) -> None:
    """
    Parse a completed SSE event buffer and fire the callback for data lines.

    SSE fields we handle:
        data: <text>   — the message content, passed to on_message
        event: <type>  — logged but not acted on (reserved for future routing)
        id: <id>       — logged but not acted on (reserved for future routing)
        : <comment>    — silently ignored (SSE keepalive comments)
    """
    for line in buffer:
        if line.startswith("data:"):
            message = line[len("data:"):].strip()
            if message:
                print(f"📨  SSE event received: {repr(message)}")
                on_message(source_label, message)

        elif line.startswith("event:"):
            event_type = line[len("event:"):].strip()
            print(f"ℹ️   SSE event type: {event_type}")

        elif line.startswith("id:"):
            event_id = line[len("id:"):].strip()
            print(f"ℹ️   SSE event id: {event_id}")

        elif line.startswith(":"):
            pass  # SSE keepalive comment — ignore
