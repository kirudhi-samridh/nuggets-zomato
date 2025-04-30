from typing import Dict, List, Type, Optional
import importlib
import json
from pathlib import Path
from loguru import logger
from tqdm import tqdm
from urllib.parse import urlparse

from .base_scraper import BaseScraper
from .universal_scraper import UniversalScraper

class ScrapingManager:
    """Manages and orchestrates restaurant scraping."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.universal_scraper = UniversalScraper(config)
        # Dictionary mapping domain patterns to scraper classes or instances
        self.scrapers: Dict[str, BaseScraper] = {}
        self._load_scrapers()
        self.results: Dict[str, Dict] = {}
    
    def _load_scrapers(self):
        """Load and initialize all available scrapers."""
        # Load predefined scrapers
        self._load_scraper('flurys_scraper', 'FlurysScraper', ['flurys.com'])
        self._load_scraper('smokin_joes_scraper', 'SmokinJoesScraper', ['smokinjoespizza.com'])
        self._load_scraper('paakashala_scraper', 'PaakashalaScraper', ['paakashala.com'])
        self._load_scraper('kailash_parbat_scraper', 'KailashParbatScraper', ['kailashparbatgroup.com'])
        
        # Load any additional scrapers defined in config
        additional_scrapers = self.config.get("additional_scrapers", [])
        for scraper_info in additional_scrapers:
            self._load_scraper(
                scraper_info.get("module", ""),
                scraper_info.get("class", ""),
                scraper_info.get("domains", [])
            )
    
    def _load_scraper(self, module_name: str, class_name: str, domains: List[str]) -> Optional[BaseScraper]:
        """Dynamically load a scraper and register it for the given domains."""
        try:
            if not module_name or not class_name or not domains:
                return None
                
            # Import the module
            module = importlib.import_module(f".{module_name}", package="scraper")
            
            # Get the scraper class
            scraper_class = getattr(module, class_name)
            
            # Instantiate the scraper
            scraper = scraper_class(self.config)
            
            # Register the scraper for each domain
            for domain in domains:
                self.scrapers[domain] = scraper
                
            logger.info(f"Successfully loaded scraper {class_name} for domains: {', '.join(domains)}")
            return scraper
        except (ImportError, AttributeError, Exception) as e:
            logger.error(f"Failed to load scraper {class_name} from {module_name}: {str(e)}")
            return None
    
    def _save_results(self, output_dir: Path):
        """Save scraping results to JSON files."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for restaurant_id, data in self.results.items():
            output_file = output_dir / f"{restaurant_id}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved results for {restaurant_id} to {output_file}")
    
    def _get_appropriate_scraper(self, url: str) -> BaseScraper:
        """Select the appropriate scraper based on the URL."""
        domain = urlparse(url).netloc.lower()
        
        # Check if we have a specific scraper for this domain
        for domain_pattern, scraper in self.scrapers.items():
            if domain_pattern in domain:
                logger.info(f"Using {scraper.__class__.__name__} for {url}")
                return scraper
        
        # Default to universal scraper for unknown domains
        logger.info(f"Using UniversalScraper for {url}")
        return self.universal_scraper
    
    def run(self, urls: List[str], output_dir: Path):
        """Run the appropriate scraper on the provided URLs."""
        logger.info(f"Starting scraping for {len(urls)} URLs")
        
        for url in tqdm(urls, desc="Scraping restaurants"):
            try:
                # Get the appropriate scraper for this URL
                scraper = self._get_appropriate_scraper(url)
                
                # Run the scraper
                result = scraper.scrape_all(url)
                
                if result:
                    try:
                        # Import here to avoid circular import
                        from knowledge_base.schema import Restaurant
                        
                        # Create a Restaurant object to validate the data
                        restaurant = Restaurant(**result)
                        restaurant_name = restaurant.restaurant_info.name
                        # Store as dictionary to ensure JSON serialization
                        self.results[restaurant_name] = restaurant.dict()
                        logger.info(f"Successfully scraped {url}")
                    except Exception as e:
                        logger.error(f"Error creating Restaurant object from {url}: {str(e)}")
                else:
                    logger.warning(f"No data scraped from {url}")
            except Exception as e:
                logger.error(f"Error scraping {url}: {str(e)}")
        
        self._save_results(output_dir)
        logger.info("Scraping completed")
        
        return self.results 