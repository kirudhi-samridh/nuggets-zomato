# Nuggets - Zomato

Restaurant Data Scraper & RAG-based Chatbot

An end-to-end Generative AI solution that allows users to ask natural language questions about restaurants and receive accurate, contextual responses based on scraped data.

## Project Structure

```
restaurant-chatbot/
├── scraper/                 # Web scraping module
│   ├── base_scraper.py     # Abstract base scraper class
│   ├── restaurant_scrapers/ # Specialized scrapers
│   ├── scraping_manager.py # Scraper orchestration
│   ├── data_processor.py   # Data cleaning and normalization
│   └── utils.py           # Helper functions
├── knowledge_base/         # Knowledge base module
│   ├── data_processor.py  # Text preprocessing
│   ├── vector_store.py    # Vector database implementation
│   ├── indexer.py        # Information indexing
│   └── schema.py         # Data schemas
├── chatbot/               # RAG-based chatbot module
│   ├── retriever.py      # Document retrieval
│   ├── generator.py      # Response generation
│   ├── rag_pipeline.py   # RAG integration
│   ├── conversation.py   # Conversation management
│   └── query_processor.py # Query processing and decomposition
├── ui/                    # User interface module
│   ├── streamlit_app.py  # Main Streamlit application
│   └── components/       # UI components
├── tests/                # Test directory
├── data/                 # Data storage
│   ├── raw/             # Raw scraped data
│   ├── processed/       # Processed data
│   ├── vector_store/    # Vector embeddings
│   └── sample/          # Sample data
├── docs/                 # Documentation
├── main.py              # Application entry point
├── config.py            # Configuration management
├── pyproject.toml       # Poetry configuration
├── run_scraper.py       # Scraper execution script
└── run_chatbot.py       # Chatbot execution script
```

## Setup and Installation

1. Install Poetry (if not already installed):
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

2. Clone the repository:
```bash
git clone https://github.com/yourusername/restaurant-chatbot.git
cd restaurant-chatbot
```

3. Install dependencies using Poetry:
```bash
poetry install
```

4. Set up environment variables:
```bash
cp .env.template .env
# Edit .env with your configuration
```

Required environment variables:
- `GROQ_API_KEY`: For LLM-based query decomposition
- `MONGODB_URI`: For conversation storage (defaults to "mongodb://localhost:27017")

5. Install external dependencies:
   - MongoDB for conversation storage
   - Tesseract OCR (optional, for PDF menu extraction)
   - Poppler (optional, for PDF processing)

## Usage

### Running the Scraper
```bash
poetry run run-scraper
```

### Running the Chatbot
```bash
poetry run run-chatbot
```

### Running the Complete Application
```bash
poetry run restaurant-chatbot
```

## Development

### Activating the Poetry Environment
```bash
poetry shell
```

### Running Tests
```bash
poetry run pytest
```

### Code Formatting
```bash
poetry run black .
poetry run isort .
```

### Type Checking
```bash
poetry run mypy .
```

## Features

### Web Scraping Capabilities
- Multi-site scraping for restaurant information
- Specialized scrapers for different restaurant website structures
- PDF menu extraction and OCR processing
- Fallback strategies for different content formats
- Restaurant-specific customization

### Knowledge Base Management
- Semantic indexing with ChromaDB vector store
- Metadata filtering for precise information retrieval
- Flexible schema with dynamic data types
- Efficient document organization and retrieval

### Advanced RAG (Retrieval Augmented Generation)
- LLM-based query decomposition for complex questions
- Multi-restaurant query support in single questions
- Intelligent results combination from multiple sources
- Progressive fallback strategies for more robust answers

### Restaurant Name Handling
- Fuzzy string matching for restaurant names
- Spelling variation tolerance and correction
- Dynamic restaurant list with automatic updates
- Multi-word restaurant name detection

### Smart Filtering
- Distinct item filtering to avoid duplicates of different sizes
- Intelligent dietary preference detection (vegetarian, non-vegetarian, vegan)
- Combined filter support in natural language
- Flexible price format handling and preservation

### Modern UI/UX
- ChatGPT-style interface with conversation history
- Past conversation browsing and retrieval
- Persistent chat history across sessions
- Responsive design with custom styling
- Clear visual separation between user and assistant messages

### Conversation Management
- MongoDB-backed conversation persistence
- Multi-user support
- Conversation context preservation
- Chat history navigation

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 