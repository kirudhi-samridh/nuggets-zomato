import streamlit as st
from pathlib import Path
import os
from loguru import logger

from knowledge_base.indexer import Indexer
from chatbot.rag_pipeline import RAGPipeline
from chatbot.retriever import Retriever
from chatbot.generator import Generator
# from chatbot.query_processor import QueryProcessor # Removed
from config import get_config

def main():
    """Run the chatbot component."""
    # Get configuration
    config = get_config()
    
    # Get Groq API key from environment variable or config
    groq_api_key = os.environ.get("GROQ_API_KEY", config.get("chatbot", {}).get("groq_api_key"))
    if not groq_api_key:
        logger.warning("No GROQ_API_KEY found. LLM-based query decomposition will be disabled.")
    
    # Initialize components
    indexer = Indexer(config["knowledge_base"])
    
    # Load knowledge base - This is now done automatically in Indexer.__init__
    # indexer.load(config["data_dir"] / "vector_store") # Removed this line
    
    # Initialize chatbot components
    retriever = Retriever(indexer, config["knowledge_base"])
    generator = Generator(config["chatbot"])
    rag_pipeline = RAGPipeline(retriever, generator, groq_api_key=groq_api_key)
    # query_processor = QueryProcessor() # Removed
    
    # Run the Streamlit app
    from ui.streamlit_app import main as run_streamlit
    run_streamlit()

if __name__ == "__main__":
    main() 