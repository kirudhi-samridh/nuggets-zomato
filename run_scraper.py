from pathlib import Path
import json
from loguru import logger

from scraper.scraping_manager import ScrapingManager
from scraper.data_processor import DataProcessor
from knowledge_base.indexer import Indexer
from knowledge_base.schema import Restaurant
from config import get_config

def main():
    """Run the scraping component."""
    # Get configuration
    config = get_config()
    
    # Initialize components
    scraper_manager = ScrapingManager(config["scraper"])
    data_processor = DataProcessor()
    indexer = Indexer(config["knowledge_base"])
    
    # Get restaurant URLs from config
    urls = config["scraper"]["restaurant_urls"]
    if not urls:
        logger.error("No restaurant URLs provided in configuration")
        return
    
    # Run scraper
    logger.info(f"Starting scraping for {len(urls)} restaurants")
    results = scraper_manager.run(urls, Path(config["data_dir"]) / "raw")
    
    # Process scraped data
    processed_data = []
    for domain, data in results.items():
        processed = data_processor.process_all_data(data)
        if processed:
            processed_data.append(processed)
    
    # Save processed data
    output_file = Path(config["data_dir"]) / "processed" / "restaurants.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(processed_data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved processed data to {output_file}")
    
    # Index processed data - convert dict to Restaurant object first
    for restaurant_data in processed_data:
        try:
            # Convert dictionary to Restaurant object
            restaurant_obj = Restaurant(**restaurant_data)
            indexer.index_restaurant(restaurant_obj)
        except Exception as e:
            logger.error(f"Error creating Restaurant object: {str(e)}")
    
    # Save knowledge base - No longer needed, ChromaDB persists automatically
    # indexer.save()
    logger.info("Scraping and indexing completed")

if __name__ == "__main__":
    main() 