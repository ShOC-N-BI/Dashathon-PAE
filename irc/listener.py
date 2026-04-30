import socket
import uuid
from typing import Callable

# ---------------------------------------------------------------------------
# PUBLIC INTERFACE
# ---------------------------------------------------------------------------

def start(
    server: str,
    port: int,
    channel: str,
    on_message: Callable[[str, str], None],
) -> None:
    """
    Connect to an IRC server and listen for messages indefinitely.

    For every user message that arrives, calls:
        on_message(username, message_text)

    All filtering, AI calls, and output logic live outside this function.
    The listener only handles connection, PING keepalive, and message parsing.

    Parameters
    ----------
    server     : IRC server hostname or IP.
    port       : IRC server port (typically 6667).
    channel    : Channel to join, including the # (e.g. "#app_dev").
    on_message : Callback that receives (username: str, message: str).
    """
    nickname = f"ABM_Listener_{uuid.uuid4().hex[:4]}"

    irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    irc.connect((server, port))

    irc.send(f"NICK {nickname}\r\n".encode())
    irc.send(f"USER {nickname} 8 * :ABM_JSON_Engine\r\n".encode())
    irc.send(f"JOIN {channel}\r\n".encode())

    print(f"📡  IRC listener connected → {server}:{port} {channel} as {nickname}")

    while True:
        data = irc.recv(4096).decode("utf-8", errors="ignore")

        for line in data.split("\r\n"):
            if not line:
                continue

            # Keep the connection alive
            if line.startswith("PING"):
                irc.send(f"PONG {line.split()[1]}\r\n".encode())
                continue

            # Only process actual user messages
            # Format: :Nick!User@Host PRIVMSG #channel :message text
            if " PRIVMSG " not in line:
                continue

            parts = line.split(":", 2)
            if len(parts) < 3:
                continue

            username = parts[1].split("!")[0] if "!" in parts[1] else "Unknown"
            message  = parts[2]

            on_message(username, message)
