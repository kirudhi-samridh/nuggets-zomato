import os
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

# Load environment variables
file_path = Path(__file__).parent
load_dotenv(file_path / ".env")

# Base paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
VECTOR_STORE_DIR = DATA_DIR / "vector_store"
STORAGE_DIR = BASE_DIR / "storage"
SAMPLE_DATA_DIR = DATA_DIR / "sample"

# Create directories if they don't exist
for directory in [RAW_DATA_DIR, PROCESSED_DATA_DIR, STORAGE_DIR, SAMPLE_DATA_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# MongoDB configuration
MONGODB_CONFIG = {
    "uri": os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
    "database": "restaurant_chatbot",
    "collections": {
        "conversations": "conversations",
        "restaurants": "restaurants",
        "users": "users"
    }
}

# Restaurant URLs to scrape
RESTAURANT_URLS = [
    "https://thalappakatti.com/",
    "https://paakashala.com/",
    "https://www.flurys.com/",
    "https://www.smokinjoespizza.com/",
    "https://www.kailashparbatgroup.com/"
]

# Scraper configuration
SCRAPER_CONFIG = {
    "user_agent": "RestaurantBot/1.0",
    "request_delay": 2,  # seconds between requests
    "max_retries": 3,
    "timeout": 30,
    "restaurant_urls": RESTAURANT_URLS,
    "max_pages": 10,
    # Configuration for website-specific scrapers
    "additional_scrapers": [
        {
            "module": "flurys_scraper",
            "class": "FlurysScraper",
            "domains": ["flurys.com"]
        },
        {
            "module": "kailash_parbat_scraper",
            "class": "KailashParbatScraper",
            "domains": ["kailashparbatgroup.com"]
        },
        {
            "module": "smokin_joes_scraper",
            "class": "SmokinJoesScraper",
            "domains": ["smokinjoespizza.com"]
        },
        {
            "module": "paakashala_scraper",
            "class": "PaakashalaScraper",
            "domains": ["paakashala.com"]
        }
    ]
}

# Knowledge base configuration (Updated for LlamaIndex + ChromaDB)
KNOWLEDGE_BASE_CONFIG = {
    "persist_dir": str(STORAGE_DIR), # Directory for ChromaDB persistence
    "chroma_collection": "restaurant_kb", # Name of the ChromaDB collection
    "search_limit": 10 # Default number of documents to retrieve (Increased)
}

# Chatbot configuration
CHATBOT_CONFIG = {
    "groq_api_key": os.getenv("GROQ_API_KEY"),
    "groq_model_name": os.getenv("GROQ_MODEL_NAME", "llama3-8b-8192"),
    "max_tokens": 1024,
    "temperature": 0.7,
    "top_p": 0.9,
    "max_history": 5
}

# UI configuration
UI_CONFIG = {
    "theme": "light",
    "page_title": "Restaurant Chatbot",
    "page_icon": "🍽️"
}

# Logging configuration
LOG_CONFIG = {
    "level": "INFO",
    "format": "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    "file": BASE_DIR / "logs" / "app.log"
}

# Create logs directory
(BASE_DIR / "logs").mkdir(exist_ok=True)

def get_config() -> Dict:
    """Get the complete configuration dictionary."""
    return {
        "base_dir": str(BASE_DIR),
        "data_dir": str(DATA_DIR),
        "mongodb": MONGODB_CONFIG,
        "scraper": SCRAPER_CONFIG,
        "knowledge_base": KNOWLEDGE_BASE_CONFIG,
        "chatbot": CHATBOT_CONFIG,
        "ui": UI_CONFIG,
        "logging": LOG_CONFIG
    } 