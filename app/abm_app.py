import streamlit as st
import pandas as pd
import json
import uuid
from datetime import datetime

# --- 1. TACTICAL LOGIC ---
def is_sensible(text):
    text = str(text).strip()
    if not text or len(text.split()) <= 2:
        return False
    alnum_count = sum(c.isalnum() for c in text)
    return (alnum_count / len(text)) > 0.3

@st.cache_data
def load_and_clean_data(file_path):
    df = pd.read_csv(file_path)
    # Detect the message column
    possible_cols = ['message', 'Message', 'text', 'Text', 'content']
    target_col = next((c for c in possible_cols if c in df.columns), df.columns[0])
    
    # Identify ID and Timestamp columns if they exist
    id_col = next((c for c in ['id', 'ID', 'requestId', 'index'] if c in df.columns), None)
    time_col = next((c for c in ['timestamp', 'time', 'date', 'lastUpdated'] if c in df.columns), None)
    user_col = next((c for c in ['user', 'originator', 'sender', 'author'] if c in df.columns), None)

    df_cleaned = df[df[target_col].apply(is_sensible)].copy()
    
    # Standardize names for the JSON mapper
    df_cleaned['standard_msg'] = df_cleaned[target_col]
    df_cleaned['standard_id'] = df_cleaned[id_col] if id_col else range(len(df_cleaned))
    df_cleaned['standard_time'] = df_cleaned[time_col] if time_col else datetime.now().isoformat()
    df_cleaned['standard_user'] = df_cleaned[user_col] if user_col else "UNKNOWN_OPERATOR"

    return df_cleaned.reset_index(drop=True)

# --- 2. JSON MAPPING FUNCTION ---
def map_to_battle_json(row):
    """Maps a single CSV row to your specific Battle JSON schema."""
    unique_id = str(uuid.uuid4())[:8] # Generates a short unique ID
    
    # This matches the schema you provided exactly
    battle_json = [{
        "id": str(row['standard_id']),
        "requestId": f"track-{unique_id}",
        "label": f"Tactical Update {unique_id}",
        "description": "Automated capture of cleaned tactical transmission.",
        "gbcId": None,
        "entitiesOfInterest": [],
        "battleEntity": [],
        "battleEffects": [], # Placeholders left blank as requested
        "chat": [
            str(row['standard_msg']),
            "PAE generated for pre-emptive and defensive options."
        ],
        "isDone": False,
        "originator": str(row['standard_user']),
        "lastUpdated": str(row['standard_time'])
    }]
    return battle_json

# --- 3. STREAMLIT UI ---
st.set_page_config(page_title="ABM Tactical JSON Feed", layout="wide")
st.title("📡 Tactical Data Link: JSON Generator")

try:
    df = load_and_clean_data("pae_data.csv")
except Exception as e:
    st.error(f"Error loading CSV: {e}")
    st.stop()

if 'msg_index' not in st.session_state:
    st.session_state.msg_index = 0

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Tactical Controls")
    if st.button("⚡ NEXT TRACK", use_container_width=True):
        if st.session_state.msg_index < len(df) - 1:
            st.session_state.msg_index += 1
        else:
            st.warning("End of Stream.")

    if st.button("🔄 RESET", use_container_width=True):
        st.session_state.msg_index = 0
        st.rerun()
    
    st.divider()
    st.write(f"**Current Track:** {st.session_state.msg_index + 1}")
    st.write(f"**Total Validated:** {len(df)}")

with col2:
    # Generate JSON for the current row
    current_row = df.iloc[st.session_state.msg_index]
    formatted_json = map_to_battle_json(current_row)
    
    st.subheader("Structured JSON Output")
    # Displaying the JSON in a format that's easy to copy
    st.json(formatted_json)
    
    # Option to copy/download
    st.download_button(
        label="Download JSON",
        data=json.dumps(formatted_json, indent=2),
        file_name=f"battle_track_{st.session_state.msg_index}.json",
        mime="application/json"
    )