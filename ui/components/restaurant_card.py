import streamlit as st
from typing import Dict, Optional

def restaurant_card(
    name: str,
    cuisine: list,
    address: str,
    rating: Optional[float] = None,
    price_range: Optional[str] = None,
    special_features: Optional[Dict] = None
):
    """Display a restaurant card with key information."""
    
    # Create card container
    with st.container():
        st.markdown("---")
        
        # Restaurant name and rating
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"### {name}")
        with col2:
            if rating:
                st.markdown(f"⭐ {rating:.1f}")
        
        # Cuisine and price range
        st.markdown(f"**Cuisine:** {', '.join(cuisine)}")
        if price_range:
            st.markdown(f"**Price Range:** {price_range}")
        
        # Address
        st.markdown(f"**Address:** {address}")
        
        # Special features
        if special_features:
            features = []
            if special_features.get("delivery"):
                features.append("🚚 Delivery")
            if special_features.get("takeout"):
                features.append("🥡 Takeout")
            if special_features.get("reservations"):
                features.append("📅 Reservations")
            if special_features.get("outdoor_seating"):
                features.append("🌳 Outdoor Seating")
            if special_features.get("wheelchair_accessible"):
                features.append("♿ Wheelchair Accessible")
            if special_features.get("parking"):
                features.append("🅿️ Parking")
            if special_features.get("wifi"):
                features.append("📶 WiFi")
            
            if features:
                st.markdown("**Features:** " + " | ".join(features))
        
        st.markdown("---") 