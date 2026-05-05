import socket
import time
import uuid
from pathlib import Path
from typing import Callable


def _read_irc_config() -> dict:
    """
    Read IRC settings fresh from .env on every reconnect.
    This allows channel/server/nickname changes from the config UI
    to take effect on the next reconnect without restarting the container.
    """
    try:
        from dotenv import dotenv_values
        for p in [Path("/app/.env"), Path(".env")]:
            if p.exists():
                v = dotenv_values(p)
                return {
                    "server":   v.get("IRC_SERVER",   "10.5.185.72"),
                    "port":     int(v.get("IRC_PORT",  "6667")),
                    "channels": [c.strip() for c in v.get("IRC_CHANNEL", "#app_dev").split(",") if c.strip()],
                    "nickname": v.get("IRC_NICKNAME", ""),
                }
    except Exception:
        pass
    return {
        "server":   "10.5.185.72",
        "port":     6667,
        "channels": ["#app_dev"],
        "nickname": "",
    }


def start(
    server: str,
    port: int,
    channel: str,
    on_message: Callable[[str, str], None],
    retry_delay: int = 10,
    nickname: str = None,
) -> None:
    """
    Connect to an IRC server and listen for messages indefinitely.
    Automatically reconnects on failure.

    IRC settings (server, port, channel, nickname) are re-read from .env
    on every reconnect — so changes made via the config UI take effect
    on the next reconnect without restarting the container.

    Parameters
    ----------
    server      : Initial IRC server (overridden by .env on reconnect).
    port        : Initial IRC port.
    channel     : Initial channel(s) — comma-separated string or single channel.
    on_message  : Callback that receives (username: str, message: str).
    retry_delay : Seconds to wait before reconnecting on failure.
    nickname    : Initial nickname (overridden by .env on reconnect).
    """
    while True:
        # Re-read config on every connection attempt so UI changes take effect
        cfg  = _read_irc_config()
        host     = cfg["server"]
        prt      = cfg["port"]
        channels = cfg["channels"]
        nick     = cfg["nickname"] if cfg["nickname"] else f"ABM_Listener_{uuid.uuid4().hex[:4]}"

        irc = None
        try:
            irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            irc.settimeout(30)
            print(f"IRC: connecting to {host}:{prt} ...")
            irc.connect((host, prt))
            irc.settimeout(None)

            irc.send(f"NICK {nick}\r\n".encode())
            irc.send(f"USER {nick} 8 * :ABM_JSON_Engine\r\n".encode())
            for chan in channels:
                irc.send(f"JOIN {chan}\r\n".encode())

            print(f"IRC: connected → {host}:{prt}  channels={channels}  nick={nick}")

            while True:
                data = irc.recv(4096).decode("utf-8", errors="ignore")

                if not data:
                    print("IRC: connection closed by server — reconnecting...")
                    break

                for line in data.split("\r\n"):
                    if not line:
                        continue

                    if line.startswith("PING"):
                        irc.send(f"PONG {line.split()[1]}\r\n".encode())
                        continue

                    if " PRIVMSG " not in line:
                        continue

                    parts = line.split(":", 2)
                    if len(parts) < 3:
                        continue

                    username = parts[1].split("!")[0] if "!" in parts[1] else "Unknown"
                    message  = parts[2]
                    on_message(username, message)

        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            print(f"IRC: connection failed ({e}) — retrying in {retry_delay}s...")
        except Exception as e:
            print(f"IRC: unexpected error ({e}) — retrying in {retry_delay}s...")
        finally:
            if irc:
                try:
                    irc.close()
                except Exception:
                    pass

        time.sleep(retry_delay)
