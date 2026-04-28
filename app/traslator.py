import socket
import uuid
import json
import re  # Added for symbol checking
from datetime import datetime

# --- CONFIGURATION ---
SERVER = "10.5.185.72"
PORT = 6667
CHANNEL = "#app_dev"
NICKNAME = f"ABM_Translator_{uuid.uuid4().hex[:4]}"

def is_clean(text):
    # 1. THE REPR CHECK (Keep this for your terminal debugging)
    # This shows you EXACTLY what the server is sending (e.g. 'test2\x00\r')
    print(f"DEBUGGING STRING: {repr(text)}")

    # 2. STRIP TO ESSENTIALS
    # Remove everything except A-Z, 0-9, and spaces.
    clean_text = "".join(re.findall(r'[a-zA-Z0-9\s]', text)).strip()
    
    # 3. SPLIT BY WHITESPACE
    # This creates a list of "real" words
    parts = clean_text.split()
    
    # 4. THE THRESHOLD
    # If there aren't at least 2 distinct parts, it's trash.
    if len(parts) < 2:
        return False
        
    # 5. LENGTH CHECK
    # Real tactical messages are rarely under 6 characters
    if len(clean_text) < 6:
        return False

    return True

def start_translator():
    try:
        irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        irc.connect((SERVER, PORT))
        
        irc.send(b"CAP LS 302\r\n")
        irc.send(f"NICK {NICKNAME}\r\n".encode())
        irc.send(f"USER {NICKNAME} 8 * :ABM_JSON_Engine\r\n".encode())
        
        print(f"--- 📡 TACTICAL FILTER ACTIVE: {CHANNEL} ---")

        while True:
            data = irc.recv(4096).decode("utf-8", errors="ignore")
            
            for line in data.split("\r\n"):
                if not line: continue
                
                # Keep server connection alive
                if line.startswith("PING"):
                    irc.send(f"PONG {line.split()[1]}\r\n".encode())
                    continue

                # STRICT CHECK: Only process lines that are actual user messages
                # A real message looks like: :Nick!User@Host PRIVMSG #channel :message
                if " PRIVMSG " in line:
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        # Extract the message content (the part after the second colon)
                        msg_content = parts[2]
                        # Extract the username
                        user = parts[1].split("!")[0] if "!" in parts[1] else "Unknown"

                        # Apply your "Ironclad" Filter
                        if is_clean(msg_content):
                            # We wrap the dict in a list [] as per your requirement
                            tactical_json = [{
                                "id": "rhino",
                                "requestId": f"track-{uuid.uuid4().hex[:6]}",
                                "label": None,
                                "description": None,
                                "gbcId": None,
                                "entitiesOfInterest": [],
                                "battleEntity": [],
                                "battleEffects": [
                                    {
                                        "id": "pae-002-e01",
                                        "effectOperator": None,
                                        "description": None,
                                        "timeWindow": None,
                                        "stateHypothesis": None,
                                        "opsLimits": [
                                            {
                                                "description": None,
                                                "battleEntity": None,
                                                "stateHypothesis": None
                                            }
                                        ],
                                        "goalContributions": [
                                            {
                                                "battleGoal": None,
                                                "effect": None
                                            }
                                        ],
                                        "recommended": True,
                                        "ranking": 1
                                    },
                                    {
                                        "id": "pae-002-e02",
                                        "effectOperator": None,
                                        "description": None,
                                        "timeWindow": None,
                                        "stateHypothesis": None,
                                        "opsLimits": [
                                            {
                                                "description": None,
                                                "battleEntity": None,
                                                "stateHypothesis": None
                                            }
                                        ],
                                        "goalContributions": [
                                            {
                                                "battleGoal": None,
                                                "effect": None
                                            }
                                        ],
                                        "recommended": False,
                                        "ranking": 2
                                    },
                                    {
                                        "id": "pae-002-e03",
                                        "effectOperator": None,
                                        "description": None,
                                        "timeWindow": None,
                                        "stateHypothesis": None,
                                        "opsLimits": [
                                            {
                                                "description": None,
                                                "battleEntity": None,
                                                "stateHypothesis": None
                                            }
                                        ],
                                        "goalContributions": [
                                            {
                                                "battleGoal": None,
                                                "effect": None
                                            }
                                        ],
                                        "recommended": False,
                                        "ranking": 3
                                    }
                                ],
                                "chat": [
                                    msg_content,
                                    "PAE generated for pre-emptive and defensive options."
                                ],
                                "isDone": False,
                                "originator": "rhino",
                                "lastUpdated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
                            }]

                            # Output to terminal
                            print(f"\n✅ FULL SCHEMA GENERATED FOR: {user}")
                            print(json.dumps(tactical_json, indent=4))
                        else:
                            print(f"🗑️ NOISE FILTERED: '{msg_content}'")
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")

if __name__ == "__main__":
    start_translator()