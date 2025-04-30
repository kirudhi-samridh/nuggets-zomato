import streamlit as st
from typing import Optional
from datetime import datetime

def chat_message(
    message: str,
    role: str = "user",
    timestamp: Optional[datetime] = None,
    avatar: Optional[str] = None
):
    """Display a chat message with custom styling."""
    
    # Set default avatar based on role
    if not avatar:
        avatar = "👤" if role == "user" else "🤖"
    
    # Format timestamp
    time_str = timestamp.strftime("%H:%M") if timestamp else ""
    
    # Create message container
    with st.container():
        # Message header
        col1, col2 = st.columns([1, 4])
        with col1:
            st.markdown(f"### {avatar}")
        with col2:
            st.markdown(f"**{role.title()}** {time_str}")
        
        # Message content
        st.markdown(message)
        
        # Add some spacing
        st.markdown("---") 