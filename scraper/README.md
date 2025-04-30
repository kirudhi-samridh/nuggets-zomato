# Restaurant Scraper System

This directory contains the scraper implementation for the restaurant chatbot. The system is designed to be modular and extensible, allowing you to add new website-specific scrapers easily.

## Architecture

- `base_scraper.py`: Abstract base class defining the interface for all scrapers
- `universal_scraper.py`: Generic scraper that can handle most restaurant websites
- `scraping_manager.py`: Manages and orchestrates the scraping process, selecting the appropriate scraper for each website
- `flurys_scraper.py`: Example of a website-specific scraper for Flurys bakery

## Core Principles

1. **Extract, Don't Assume**: Only extract information that's explicitly present on the website. Don't fill in default values for missing information.
2. **Accuracy Over Completeness**: It's better to return partial but accurate data than complete but potentially incorrect data.
3. **Explicit Attribution**: Make it clear which data comes from the website versus which is inferred or assumed (if any inference is necessary).

## Adding a New Scraper

To add a new scraper for a specific restaurant website:

1. Create a new Python file for your scraper (e.g., `my_restaurant_scraper.py`)
2. Extend the `BaseScraper` class and implement all required methods
3. Add your scraper to the configuration in `config.py`

### Step 1: Create Your Scraper Class

```python
# my_restaurant_scraper.py
from typing import Dict, List
from .base_scraper import BaseScraper

class MyRestaurantScraper(BaseScraper):
    """Scraper for MyRestaurant website."""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.base_url = "https://myrestaurant.com/"
    
    def scrape_restaurant_info(self, url: str) -> Dict:
        # Implementation for scraping restaurant info
        # Only include information that's explicitly on the website
        # ...
    
    def scrape_menu(self, url: str) -> List[Dict]:
        # Implementation for scraping menu items
        # ...
    
    def scrape_special_features(self, url: str) -> Dict:
        # Implementation for scraping special features
        # Only include features that are explicitly mentioned
        # ...
    
    def scrape_operating_hours(self, url: str) -> Dict:
        # Implementation for scraping operating hours
        # Only include hours that are explicitly stated
        # ...
```

### Step 2: Configure Your Scraper

Add your scraper to the configuration in `config.py`:

```python
# In config.py
SCRAPER_CONFIG = {
    # ... existing config ...
    "additional_scrapers": [
        {
            "module": "my_restaurant_scraper",
            "class": "MyRestaurantScraper",
            "domains": ["myrestaurant.com", "www.myrestaurant.com"]
        }
    ]
}
```

### Step 3: Test Your Scraper

Create a test script for your scraper:

```python
# test_my_restaurant_scraper.py
import json
from pathlib import Path
from loguru import logger

from scraper.my_restaurant_scraper import MyRestaurantScraper
from config import get_config

def main():
    # Get configuration
    config = get_config()
    
    # Initialize scraper
    scraper = MyRestaurantScraper(config["scraper"])
    
    # URL to scrape
    url = "https://myrestaurant.com/"
    
    # Run scraper
    result = scraper.scrape_all(url)
    
    # Save results
    output_dir = Path(config["data_dir"]) / "test"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / "my_restaurant_test.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"Saved test results to {output_file}")

if __name__ == "__main__":
    main()
```

## Tips for Creating a Good Scraper

1. **No Default Values**: Do not provide default values for information that isn't on the website (like operating hours). Return empty values instead.
2. **Robustness**: Always wrap parsing logic in try-except blocks to handle unexpected HTML structures.
3. **Verify Existence**: Check if elements exist before extracting data from them.
4. **Explicit Extraction**: Only extract data that is explicitly stated on the website.
5. **Selective Field Inclusion**: Only include fields in the result if they have valid data.
6. **Rate Limiting**: Respect the website's robots.txt and implement appropriate delays between requests.
7. **CSS Selectors**: Use specific CSS selectors to extract data whenever possible.
8. **Regex**: For unstructured data, use regular expressions as a fallback.

## Data Schema

All scrapers must return data conforming to the following schema, but fields should be omitted if the data isn't present on the website:

- `restaurant_info`: Basic information about the restaurant (name, address, contact)
- `menu_items`: List of menu items with names, descriptions, prices, and categories
- `special_features`: Dictionary of boolean values indicating available features (only include features explicitly mentioned)
- `operating_hours`: Dictionary of opening and closing times for each day of the week (only include days explicitly stated)

See `knowledge_base/schema.py` for the complete Pydantic models. 