import streamlit as st
from pathlib import Path
import json
import re # Import re for keyword searching
import uuid # For new chat IDs
from datetime import datetime
import difflib # For fuzzy string matching
from loguru import logger
from typing import Dict, Optional, List # Import types

from chatbot.rag_pipeline import RAGPipeline
from chatbot.retriever import Retriever
from chatbot.generator import Generator
from chatbot.conversation import Conversation, Message
from knowledge_base.indexer import Indexer
from config import get_config

# Custom CSS to make the UI more similar to ChatGPT
def apply_custom_css():
    st.markdown("""
    <style>
    .stApp {
        max-width: 1200px;
        margin: 0 auto;
    }
    
    /* Main chat area styling */
    .main-content {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 20px;
    }
    
    /* Message styling */
    .chat-message {
        padding: 1.5rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        display: flex;
        flex-direction: row;
        align-items: flex-start;
        gap: 0.75rem;
    }
    
    .chat-message.user {
        background-color: #f7f7f8;
    }
    
    .chat-message.assistant {
        background-color: #ffffff;
        border: 1px solid #e5e5e5;
    }
    
    /* Sidebar chat history styling */
    .chat-list-item {
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 8px;
        cursor: pointer;
        transition: background-color 0.3s;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    
    .chat-list-item:hover {
        background-color: #f0f0f0;
    }
    
    .chat-list-item.active {
        background-color: #e1e1e1;
        font-weight: bold;
    }
    
    /* Make the sidebar chat items clickable with custom styling */
    div[data-testid="stSidebarNav"] li {
        cursor: pointer;
        border-radius: 5px;
        padding: 5px;
    }
    
    div[data-testid="stSidebarNav"] li:hover {
        background-color: rgba(151, 166, 195, 0.15);
    }
    </style>
    """, unsafe_allow_html=True)

# Define common restaurant names for better matching
KNOWN_RESTAURANTS = [
    "smokin joes pizza", 
    "thalappakatti", 
    "kailash parbat",
    "dominos",
    "mcdonalds",
    "burger king",
    "pizza hut"
]

def fuzzy_match_restaurant(name: str, threshold: float = 0.8) -> Optional[str]:
    """Find closest matching restaurant name using fuzzy string matching."""
    if not name:
        return None
        
    # Try direct matching first
    for restaurant in KNOWN_RESTAURANTS:
        if restaurant.lower() in name.lower():
            return restaurant
    
    # If no direct match, try fuzzy matching
    matches = difflib.get_close_matches(name.lower(), [r.lower() for r in KNOWN_RESTAURANTS], n=1, cutoff=threshold)
    if matches:
        # Get the index of the matched restaurant to return the original casing
        idx = [r.lower() for r in KNOWN_RESTAURANTS].index(matches[0])
        logger.info(f"Fuzzy matched '{name}' to known restaurant '{KNOWN_RESTAURANTS[idx]}'")
        return KNOWN_RESTAURANTS[idx]
    
    # No match found
    return name

def extract_restaurant_names(query: str) -> List[str]:
    """Extract multiple restaurant names from a query using improved patterns."""
    query_lower = query.lower()
    restaurant_names = []
    
    # Patterns to match restaurant names - more restrictive to avoid over-matching
    restaurant_patterns = [
        r'in\s+([\w\s\']+?)\s+restaurant',  # "in thalappakatti restaurant"
        r'at\s+([\w\s\']+?)\s+restaurant',  # "at thalappakatti restaurant"
        r'from\s+([\w\s\']+?)\s+restaurant', # "from thalappakatti restaurant"
        r'in\s+([\w\s\']+?)(?:\s+and|\s+[,.]|\s*$)', # "in thalappakatti" or "in smokin joes pizza and"
        r'at\s+([\w\s\']+?)(?:\s+and|\s+[,.]|\s*$)', # "at thalappakatti" or "at smokin joes pizza."
        r'from\s+([\w\s\']+?)(?:\s+and|\s+[,.]|\s*$)', # "from thalappakatti" or "from smokin joes pizza"
        r'([\w\s\']+?)\s+restaurant', # "thalappakatti restaurant" (no preposition)
        r'([\w\s\']+?)\s+menu' # "smokin joes pizza menu"
    ]
    
    # Apply each pattern
    for pattern in restaurant_patterns:
        for match in re.finditer(pattern, query_lower):
            restaurant_name = match.group(1).strip()
            if restaurant_name and restaurant_name not in [r.lower() for r in restaurant_names]:
                # Apply fuzzy matching
                matched_name = fuzzy_match_restaurant(restaurant_name)
                if matched_name and matched_name not in restaurant_names:
                    restaurant_names.append(matched_name)
    
    return restaurant_names

def parse_query_for_filters(query_text: str) -> Optional[Dict]:
    """Extract dietary filters and restaurant name from the query."""
    query_lower = query_text.lower()
    filters = {}
    
    logger.debug(f"Analyzing query for filters: '{query_lower}'")
    
    # Check for special query parameters
    if "distinct" in query_lower:
        filters["distinct"] = "true"
        logger.info("Detected 'distinct' parameter in query")
    
    # Map filter keywords to metadata keys and STRING values
    filter_map = {
        'vegetarian': {"vegetarian": "true"},
        'vegan': {"vegan": "true"},
        'gluten-free': {"gluten_free": "true"},
        'gluten free': {"gluten_free": "true"},
        # Add non-vegetarian filters
        'non-veg': {"vegetarian": "false"},
        'non veg': {"vegetarian": "false"},
        'non vegetarian': {"vegetarian": "false"},
        'meat': {"vegetarian": "false"},
        'non-vegetarian': {"vegetarian": "false"}
    }
    
    found_filter = False
    # First check direct keyword matches
    for keyword, filter_criteria in filter_map.items():
        if re.search(r'\b' + re.escape(keyword) + r'\b', query_lower): 
            filters.update(filter_criteria) # Add the specific filter
            # Ensure we only filter for menu items when a dietary flag is present
            filters["doc_type"] = "menu_item" 
            found_filter = True
            logger.info(f"Detected filter keyword: '{keyword}', applying filters: {filters}")
            break 
    
    # If no direct match, check for phrase patterns
    if not found_filter:
        # Common patterns for non-veg requests
        if re.search(r'\b(non-?veg\w*|meat\w*)\b.*(option|dish|item|food)', query_lower):
            filters.update({"vegetarian": "false"})
            filters["doc_type"] = "menu_item"
            found_filter = True
            logger.info(f"Detected non-vegetarian phrase pattern, applying filter: vegetarian=false")
        # More general pattern for just asking about non-veg without specific terms
        elif re.search(r'\b(non-?veg\w*|meat\w*)\b', query_lower):
            filters.update({"vegetarian": "false"})
            filters["doc_type"] = "menu_item"
            found_filter = True
            logger.info(f"Detected general non-vegetarian term, applying filter: vegetarian=false")

    # Extract restaurant names from the query
    restaurant_names = extract_restaurant_names(query_lower)
    
    # Only apply restaurant filter if exactly one restaurant is detected
    # If multiple restaurants are detected, we'll need to modify the retrieval logic
    # to handle multiple restaurants (this would need to be implemented in the retriever)
    if restaurant_names:
        logger.info(f"Detected {len(restaurant_names)} restaurant(s): {restaurant_names}")
        
        # For now, just use the first restaurant name
        if len(restaurant_names) > 0:
            restaurant_name = restaurant_names[0]
            filters["doc_type"] = filters.get("doc_type", "menu_item")
            filters["restaurant_id_lower"] = restaurant_name.lower()
            found_filter = True
            logger.info(f"Using restaurant filter: 'restaurant_id_lower'='{restaurant_name.lower()}'")
            
        # If more than one restaurant, log a warning
        if len(restaurant_names) > 1:
            logger.warning(f"Multiple restaurants detected: {restaurant_names}. Currently using only the first one: {restaurant_names[0]}")

    # Add debug filter options
    if "debug_menu_items" in query_lower:
        # Just return menu items without filters
        logger.info("Debug mode: Showing all menu items")
        filters = {"doc_type": "menu_item"}
        found_filter = True
    
    # Add debug log for final filters
    if filters:
        logger.debug(f"Final filter configuration: {filters}")

    return filters if found_filter else None

def initialize_components():
    """Initialize all necessary components."""
    config = get_config()
    kb_config = config["knowledge_base"]
    chatbot_config = config["chatbot"]
    
    # Get Groq API key
    groq_api_key = chatbot_config.get("groq_api_key")
    
    # Initialize knowledge base
    indexer = Indexer(kb_config)
    
    # Initialize chatbot components
    retriever = Retriever(indexer, kb_config)
    generator = Generator(chatbot_config)
    rag_pipeline = RAGPipeline(retriever, generator, groq_api_key=groq_api_key)
    
    return rag_pipeline

def get_chat_title(messages: List) -> str:
    """Generate a title from the first user message in a conversation."""
    if not messages:
        return "New Chat"
    
    # Find the first user message
    for msg in messages:
        if msg.role == "user":
            # Truncate message to create a title
            content = msg.content.strip()
            if len(content) > 30:
                return content[:27] + "..."
            return content
    
    return "New Chat"

def get_conversation_list(conversation: Conversation) -> List[Dict]:
    """Get list of all conversations from MongoDB."""
    chat_list = []
    try:
        # Get the MongoDB collection
        collection = conversation.collection
        # Query for all distinct chat_ids
        chat_ids = collection.distinct("chat_id")
        
        for chat_id in chat_ids:
            # Get the first conversation data
            chat_data = collection.find_one({"chat_id": chat_id})
            if chat_data and "messages" in chat_data:
                # Create a message list
                messages = [
                    Message(
                        role=msg["role"],
                        content=msg["content"],
                        timestamp=msg.get("timestamp", datetime.now())
                    )
                    for msg in chat_data["messages"]
                ]
                
                # Generate a title
                title = get_chat_title(messages)
                
                # Get the timestamp of the most recent message
                latest_timestamp = max([msg.get("timestamp", datetime.now()) for msg in chat_data["messages"]])
                
                chat_list.append({
                    "chat_id": chat_id,
                    "title": title,
                    "timestamp": latest_timestamp
                })
        
        # Sort by most recent first
        chat_list.sort(key=lambda x: x["timestamp"], reverse=True)
        
    except Exception as e:
        logger.error(f"Error retrieving conversation list: {str(e)}")
    
    return chat_list

def load_conversation(chat_id: str, conversation: Conversation) -> Conversation:
    """Load a specific conversation by ID."""
    try:
        # Create a new conversation object with the specified chat_id
        new_conversation = Conversation(
            max_history=conversation.max_history,
            mongo_uri=conversation.client.address[0]
        )
        new_conversation.chat_id = chat_id
        
        # Load the messages
        new_conversation.get_history()
        
        return new_conversation
    except Exception as e:
        logger.error(f"Error loading conversation {chat_id}: {str(e)}")
        return conversation

def main():
    """Main Streamlit application."""
    # Set page config first - must be the first Streamlit command
    st.set_page_config(
        page_title="Restaurant Chatbot",
        page_icon="🍽️",
        layout="wide"
    )
    
    # Apply custom CSS after page config
    apply_custom_css()
    
    # Get configuration
    config = get_config()
    
    # Initialize session state for conversations
    if "conversation" not in st.session_state:
        st.session_state.conversation = Conversation(
            max_history=config["chatbot"]["max_history"],
            mongo_uri=config["mongodb"]["uri"]
        )
    
    if "conversations" not in st.session_state:
        st.session_state.conversations = get_conversation_list(st.session_state.conversation)
    
    if "current_chat_id" not in st.session_state:
        st.session_state.current_chat_id = st.session_state.conversation.chat_id
        
    if "rag_pipeline" not in st.session_state:
        with st.spinner("Initializing AI components..."):
            st.session_state.rag_pipeline = initialize_components()
    
    # Sidebar for chat history
    with st.sidebar:
        st.title("Restaurant Chatbot")
        
        # New chat button
        if st.button("➕ New Chat", key="new_chat"):
            # Create a new conversation
            new_conversation = Conversation(
                max_history=config["chatbot"]["max_history"],
                mongo_uri=config["mongodb"]["uri"]
            )
            st.session_state.conversation = new_conversation
            st.session_state.current_chat_id = new_conversation.chat_id
            # Refresh conversation list
            st.session_state.conversations = get_conversation_list(new_conversation)
            st.rerun()
        
        st.markdown("---")
        st.subheader("Chat History")
        
        # Display chat history
        for chat in st.session_state.conversations:
            chat_id = chat["chat_id"]
            title = chat["title"]
            
            # Determine if this is the active chat
            is_active = chat_id == st.session_state.current_chat_id
            
            # Display the chat with appropriate styling
            if st.sidebar.button(
                f"{'📌 ' if is_active else '📄 '}{title}", 
                key=f"chat_{chat_id}",
                use_container_width=True,
                type="primary" if is_active else "secondary"
            ):
                # Load the selected conversation
                st.session_state.conversation = load_conversation(chat_id, st.session_state.conversation)
                st.session_state.current_chat_id = chat_id
                st.rerun()
        
        st.markdown("---")
        
        # Settings section
        with st.expander("ℹ️ About"):
            st.markdown("""
            This chatbot uses advanced AI to provide information about restaurants.
            It can understand natural language questions and provide relevant answers
            based on restaurant data.
            """)
        
        # Clear all conversations button
        if st.button("🗑️ Clear All Chats", key="clear_all"):
            # Confirm deletion
            if st.button("⚠️ Confirm Clear All", key="confirm_clear"):
                try:
                    # Get all chat IDs
                    collection = st.session_state.conversation.collection
                    collection.delete_many({})
                    
                    # Create a new conversation
                    new_conversation = Conversation(
                        max_history=config["chatbot"]["max_history"],
                        mongo_uri=config["mongodb"]["uri"]
                    )
                    st.session_state.conversation = new_conversation
                    st.session_state.current_chat_id = new_conversation.chat_id
                    # Refresh conversation list
                    st.session_state.conversations = []
                    st.rerun()
                except Exception as e:
                    logger.error(f"Error clearing all conversations: {str(e)}")
                    st.error("Failed to clear conversations.")
    
    # Main content area
    main_container = st.container()
    with main_container:
        # Display conversation title
        conversation_title = get_chat_title(st.session_state.conversation.get_history())
        st.header(conversation_title)
        
        # Chat container
        chat_container = st.container()
        with chat_container:
            # Display messages
            messages = st.session_state.conversation.get_history()
            for message in messages:
                with st.chat_message(message.role):
                    st.write(message.content)
    
    # Chat input
    if prompt := st.chat_input("Ask me about restaurant menus, dishes, or dietary options..."):
        # Display user message
        with st.chat_message("user"):
            st.write(prompt)
        
        # Add user message to conversation
        st.session_state.conversation.add_message("user", prompt)
        
        # Parse query for filters
        filters = parse_query_for_filters(prompt)
        
        # Process query with RAG pipeline, passing filters if any
        with st.spinner("Thinking..."):
            response = st.session_state.rag_pipeline.process_query(prompt, filters=filters)
        
        # Add assistant response to conversation
        st.session_state.conversation.add_message("assistant", response)
        
        # Display assistant response
        with st.chat_message("assistant"):
            st.write(response)
        
        # Refresh the conversation list to update titles
        st.session_state.conversations = get_conversation_list(st.session_state.conversation)
        
        # Rerun to update UI
        st.rerun()

if __name__ == "__main__":
    main() 