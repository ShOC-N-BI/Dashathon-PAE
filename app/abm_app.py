import streamlit as st
import socket
import threading
import uuid
import queue
import time
from datetime import datetime

# --- 1. GLOBAL TACTICAL BUFFERS ---
# We use standard Python Queues because they are thread-safe and don't rely on Streamlit State
if 'mission_buffer' not in globals():
    mission_buffer = queue.Queue()
if 'log_buffer' not in globals():
    log_buffer = []

# --- 2. THE MANUAL SOCKET LISTENER (THREAD-SAFE) ---
def irc_manual_link(server, port, channel, nickname, password=None):
    try:
        log_buffer.append(f"📡 INIT: Dialing {server}:6667...")
        irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        irc.settimeout(15)
        irc.connect((server, 6667))
        
        # 1. Start Handshake
        irc.send(b"CAP LS 302\r\n")
        if password:
            irc.send(f"PASS {password}\r\n".encode())
        irc.send(f"NICK {nickname}\r\n".encode())
        irc.send(f"USER {nickname} 8 * :ABM_Operator\r\n".encode())
        
        while True:
            try:
                raw_data = irc.recv(4096)
                if not raw_data: break
                data = raw_data.decode("utf-8", errors="ignore")
                
                # --- TERMINAL SCAN: Read these lines in your PowerShell window! ---
                for line in data.split("\r\n"):
                    if not line: continue
                    print(f"📡 SERVER SAYS: {line}") 
                    
                    if line.startswith("PING"):
                        irc.send(f"PONG {line.split()[1]}\r\n".encode())
                    
                    if "CAP" in line and "LS" in line:
                        irc.send(b"CAP END\r\n")

                    # Success Codes (Welcome / End of MOTD)
                    if " 001 " in line or " 376 " in line:
                        log_buffer.append("✅ CONNECTED. Waiting 2s to join...")
                        time.sleep(2) # Tactical pause
                        irc.send(f"JOIN {channel}\r\n".encode())
                        log_buffer.append(f"📡 JOIN SENT: {channel}")

                    # Error Codes: 471 (Full), 473 (Invite Only), 474 (Banned), 475 (Bad Key)
                    if any(code in line for code in [" 471 ", " 473 ", " 474 ", " 475 "]):
                        log_buffer.append(f"❌ JOIN FAILED: {line.split(':')[-1]}")

                    # Capture Chat (PRIVMSG)
                    if "PRIVMSG" in line:
                        parts = line.split(":", 2)
                        if len(parts) >= 3:
                            user = parts[1].split("!")[0]
                            msg_content = parts[2]
                            mission_buffer.put({
                                "msg": msg_content,
                                "user": user,
                                "time": datetime.now().isoformat()
                            })
                            log_buffer.append(f"📩 INTERCEPT: Msg from {user}")
                            
            except socket.timeout:
                continue 
    except Exception as e:
        log_buffer.append(f"❌ ERROR: {str(e)}")

# --- 3. STREAMLIT UI INITIALIZATION ---
st.set_page_config(page_title="ABM Raw Link", layout="wide")

# Ensure the background thread only starts ONCE
if 'thread_started' not in st.session_state:
    bot_name = f"ABM_{uuid.uuid4().hex[:4]}"
    thread = threading.Thread(
        target=irc_manual_link, 
        args=("10.5.185.72", 8000, "#app_dev", bot_name),
        daemon=True
    )
    thread.start()
    st.session_state.thread_started = True

# --- 4. UI LAYOUT ---
st.title("📡 Live Tactical Socket: #app_dev")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Tactical Controls")
    
    # Check how many items are in the global queue
    q_size = mission_buffer.qsize()
    st.metric("Buffered Tracks", q_size)

    if st.button("⚡ PULL NEXT TRACK", use_container_width=True):
        if not mission_buffer.empty():
            track = mission_buffer.get()
            st.session_state.current_json = {
                "id": f"track-{uuid.uuid4().hex[:6]}",
                "chat": [track['msg']],
                "originator": track['user'],
                "lastUpdated": track['time']
            }
        else:
            st.warning("No data in buffer.")

    if st.button("🔄 REFRESH UI"):
        st.rerun()

    st.divider()
    st.subheader("System Events")
    # Display logs from our global list
    for log in reversed(log_buffer[-10:]):
        st.caption(log)

with col2:
    st.subheader("JSON Output")
    if 'current_json' in st.session_state:
        st.json(st.session_state.current_json)
    else:
        st.info("Awaiting acquisition. Send a message in IRC to trigger.")

# Auto-refresh the UI every 2 seconds if the thread is active
st.empty() 
time.sleep(20)
st.rerun()