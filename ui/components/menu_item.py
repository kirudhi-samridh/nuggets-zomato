import streamlit as st
from typing import Dict, Optional

def menu_item(
    name: str,
    description: str,
    price: float,
    category: str,
    dietary_info: Optional[Dict[str, bool]] = None
):
    """Display a menu item with its details."""
    
    # Create item container
    with st.container():
        st.markdown("---")
        
        # Item name and price
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"### {name}")
        with col2:
            st.markdown(f"**${price:.2f}**")
        
        # Category
        st.markdown(f"**Category:** {category}")
        
        # Description
        st.markdown(description)
        
        # Dietary information
        if dietary_info:
            dietary_tags = []
            if dietary_info.get("vegetarian"):
                dietary_tags.append("🥬 Vegetarian")
            if dietary_info.get("vegan"):
                dietary_tags.append("🌱 Vegan")
            if dietary_info.get("gluten_free"):
                dietary_tags.append("🌾 Gluten-Free")
            
            if dietary_tags:
                st.markdown("**Dietary:** " + " | ".join(dietary_tags))
        
        st.markdown("---") 