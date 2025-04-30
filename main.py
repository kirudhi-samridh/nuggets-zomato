import streamlit as st
from pathlib import Path
import json
from loguru import logger

from scraper.scraping_manager import ScrapingManager
from scraper.data_processor import DataProcessor
from knowledge_base.indexer import Indexer
from chatbot.rag_pipeline import RAGPipeline
from .retriever import Retriever
from .generator import Generator
from config import get_config

def initialize_components():
    """Initialize all necessary components."""
    config = get_config()
    
    # Initialize scraper
    scraper_manager = ScrapingManager(config["scraper"])
    data_processor = DataProcessor()
    
    # Initialize knowledge base
    indexer = Indexer(config["knowledge_base"])
    
    # Initialize chatbot components
    retriever = Retriever(indexer, config["knowledge_base"])
    generator = Generator(config["chatbot"])
    rag_pipeline = RAGPipeline(retriever, generator)
    
    return {
        "scraper_manager": scraper_manager,
        "data_processor": data_processor,
        "indexer": indexer,
        "rag_pipeline": rag_pipeline,
    }

def main():
    """Main application entry point."""
    # Initialize components
    components = initialize_components()
    
    # Run the Streamlit app
    from ui.streamlit_app import main as run_streamlit
    run_streamlit()

if __name__ == "__main__":
    main() 