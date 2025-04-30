from abc import ABC, abstractmethod
import time
from typing import Dict, List, Optional
import requests
from bs4 import BeautifulSoup
from loguru import logger

class BaseScraper(ABC):
    """Abstract base class for restaurant scrapers."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config["user_agent"]
        })
    
    def _make_request(self, url: str) -> Optional[BeautifulSoup]:
        """Make an HTTP request with retry logic and rate limiting."""
        for attempt in range(self.config["max_retries"]):
            try:
                response = self.session.get(
                    url,
                    timeout=self.config["timeout"]
                )
                response.raise_for_status()
                time.sleep(self.config["request_delay"])
                return BeautifulSoup(response.text, "html.parser")
            except requests.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}/{self.config['max_retries']}): {str(e)}")
                if attempt == self.config["max_retries"] - 1:
                    logger.error(f"Failed to fetch {url} after {self.config['max_retries']} attempts")
                    return None
                time.sleep(self.config["request_delay"] * (attempt + 1))
    
    @abstractmethod
    def scrape_restaurant_info(self, url: str) -> Dict:
        """Scrape basic restaurant information."""
        pass
    
    @abstractmethod
    def scrape_menu(self, url: str) -> List[Dict]:
        """Scrape restaurant menu items."""
        pass
    
    @abstractmethod
    def scrape_special_features(self, url: str) -> Dict:
        """Scrape special features and dietary information."""
        pass
    
    @abstractmethod
    def scrape_operating_hours(self, url: str) -> Dict:
        """Scrape operating hours and contact information."""
        pass
    
    def scrape_all(self, url: str) -> Dict:
        """Scrape all restaurant information."""
        try:
            restaurant_info = self.scrape_restaurant_info(url)
            menu_items = self.scrape_menu(url)
            special_features = self.scrape_special_features(url)
            operating_hours = self.scrape_operating_hours(url)
            
            return {
                "restaurant_info": restaurant_info,
                "menu_items": menu_items,
                "special_features": special_features,
                "operating_hours": operating_hours
            }
        except Exception as e:
            logger.error(f"Error scraping {url}: {str(e)}")
            return {} 