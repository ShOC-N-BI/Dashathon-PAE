import streamlit as st
import pandas as pd
import re

# --- 1. TACTICAL CLEANING LOGIC ---
def is_sensible(text):
    """
    ABM Filter: Removes short chatter and non-alphanumeric noise.
    """
    text = str(text).strip()
    # Reject if message is empty or less than 3 words (e.g., 'Copy that', 'Wilco')
    if not text or len(text.split()) <= 2:
        return False
    
    # Calculate alphanumeric ratio to filter out gibberish/symbols
    alnum_count = sum(c.isalnum() for c in text)
    return (alnum_count / len(text)) > 0.3

@st.cache_data
def load_and_clean_data(file_path):
    """
    Loads CSV and automatically identifies the message column.
    """
    df = pd.read_csv(file_path)
    
    # Auto-detect the correct column
    possible_cols = ['message', 'Message', 'text', 'Text', 'content', 'Body', 'RAW_TEXT']
    target_col = None
    
    for col in possible_cols:
        if col in df.columns:
            target_col = col
            break
            
    if not target_col:
        # Fallback to the first column if no matches found
        target_col = df.columns[0]
    
    # Apply the ABM sensible filter
    df_cleaned = df[df[target_col].apply(is_sensible)].copy()
    
    # Standardize column name for the UI logic
    df_cleaned = df_cleaned.rename(columns={target_col: 'message'})
    
    return df_cleaned.reset_index(drop=True)

# --- 2. STREAMLIT UI SETUP ---
st.set_page_config(page_title="ABM Tactical Feed", page_icon="📡", layout="wide")

st.title("📡 Eye in the Sky: Tactical Feed")
st.markdown("---")

# Load the data
try:
    # Ensure this filename matches your actual CSV file in the /app folder
    df = load_and_clean_data("pae_data.csv")
except FileNotFoundError:
    st.error("🚨 CRITICAL: 'pae_data.csv' not found in the /app directory.")
    st.stop()

# Initialize Session State to track progress through the log
if 'msg_index' not in st.session_state:
    st.session_state.msg_index = 0

# --- 3. MAIN DISPLAY AREA ---
col1, col2 = st.columns([1, 3])

with col1:
    st.subheader("Control Panel")
    if st.button("⚡ NEXT TRACK", use_container_width=True):
        if st.session_state.msg_index < len(df) - 1:
            st.session_state.msg_index += 1
        else:
            st.warning("END OF DATA STREAM.")

    if st.button("🔄 RESET FEED", use_container_width=True):
        st.session_state.msg_index = 0
        st.rerun()

with col2:
    # Display the current cleaned message
    if len(df) > 0:
        current_msg = df.iloc[st.session_state.msg_index]['message']
        
        st.info(f"**DATA LINK STATUS: ACTIVE | TRACK {st.session_state.msg_index + 1} of {len(df)}**")
        
        # Displaying in 'code' block for that tactical monitor look
        st.code(current_msg, language="text")
        
        # Metadata mockup
        st.caption(f"Source: pae_data.csv | Logic: Alphanumeric Filter > 0.3")
    else:
        st.error("No valid tactical data found after cleaning.")

# --- 4. SIDEBAR LOGS ---
st.sidebar.header("System Intelligence")
st.sidebar.markdown(f"""
**Persona:** Air Battle Manager  
**Filter State:** NOMINAL  
**Validated Tracks:** {len(df)}  
""")

if st.sidebar.checkbox("Show Raw Data Preview"):
    st.sidebar.write(df.head(10))