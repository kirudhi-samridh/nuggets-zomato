from typing import Dict, List, Optional
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup, Tag
from loguru import logger

from .base_scraper import BaseScraper


class FlurysScraper(BaseScraper):
    """Scraper for Flurys bakery website."""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.base_url = "https://www.flurys.com/"
    
    def scrape_restaurant_info(self, url: str) -> Dict:
        """Scrape basic restaurant information."""
        soup = self._make_request(url)
        if not soup:
            logger.error(f"Failed to fetch {url}")
            return {}
        
        # Default values
        name = "Flurys"
        address = ""
        phone = ""
        email = ""
        website = url
        cuisine = []
        
        # Try to extract name from title
        try:
            title_element = soup.find('title')
            if title_element:
                title_text = title_element.text.strip()
                if title_text and "Flurys" in title_text:
                    name = "Flurys"
        except Exception as e:
            logger.warning(f"Error extracting restaurant name: {str(e)}")
            
        # Look for specific address information in footer
        footer = soup.find("footer")
        if footer:
            address_section = footer.select_one('.footer__address, .contact-address')
            if address_section:
                address = address_section.text.strip()
            else:
                # Default historical address since it's known
                address = "Park Street, Kolkata"
        
        # Try to extract contact information if available
        try:
            # Look for any contact information on the page
            contact_section = soup.find("footer")
            if contact_section:
                # Extract any phone numbers using regex pattern
                phone_pattern = re.compile(r'[\+\(]?[0-9][0-9 .\-\(\)]{8,}[0-9]')
                phone_matches = phone_pattern.findall(contact_section.text)
                if phone_matches:
                    phone = phone_matches[0]
                
                # Extract email if available
                email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
                email_matches = email_pattern.findall(contact_section.text)
                if email_matches:
                    email = email_matches[0]
        except Exception as e:
            logger.warning(f"Error extracting contact information: {str(e)}")
        
        # Try to determine the cuisine based on the content
        try:
            page_text = soup.get_text().lower()
            
            if "bakery" in page_text or "bake" in page_text:
                cuisine.append("Bakery")
            
            if "confectionery" in page_text or "confection" in page_text:
                cuisine.append("Confectionery")
                
            if "cafe" in page_text or "coffee" in page_text or "tea" in page_text:
                cuisine.append("Cafe")
                
            # If no cuisine found, check page headers or other elements
            if not cuisine:
                for heading in soup.find_all(['h1', 'h2', 'h3']):
                    heading_text = heading.text.lower()
                    if any(keyword in heading_text for keyword in ["bakery", "confectionery", "cafe"]):
                        cuisine.append("Bakery & Confectionery")
                        break
        except Exception as e:
            logger.warning(f"Error determining cuisine: {str(e)}")
            
        # Set a default cuisine only if we couldn't find any
        if not cuisine:
            cuisine = ["Bakery & Confectionery"]
        
        # Add this to cuisine and description
        if "tearoom" not in page_text and "park street" not in page_text.lower():
            description = "Flurys, the legendary tearoom on fashionable Park Street in Kolkata was founded in 1927 by a Swiss expatriate couple Mr. and Mrs. J. Flurys."
        
        return {
            "name": name,
            "address": address,
            "phone": phone,
            "email": email,
            "website": website,
            "cuisine": cuisine
        }
    
    def scrape_menu(self, url: str) -> List[Dict]:
        """Scrape restaurant menu items."""
        soup = self._make_request(url)
        if not soup:
            logger.error(f"Failed to fetch {url}")
            return []
        
        menu_items = []
        
        # First, collect items from the homepage which shows best selling products
        self._scrape_products_from_page(soup, menu_items)
        
        # Scrape menu items from each category page
        categories = ["Cakes", "Festive Dry Cakes", "Breads", "Pastries", 
                      "Chocolates", "Savouries", "Cookies", "Brownies"]
        
        for category in categories:
            # Create category URL by converting category name to URL format
            category_url = urljoin(self.base_url, f"collections/{category.lower().replace(' ', '-')}")
            logger.info(f"Scraping category: {category} from {category_url}")
            
            # Make request to category page
            category_soup = self._make_request(category_url)
            if not category_soup:
                logger.error(f"Failed to fetch category page: {category_url}")
                continue
                
            # Scrape products from this category page
            self._scrape_products_from_page(category_soup, menu_items, default_category=category)
            
            # Check if there's pagination and scrape additional pages
            pagination = category_soup.select('.pagination a')
            if pagination:
                # Get last page number
                try:
                    last_page = max([int(a.text.strip()) for a in pagination if a.text.strip().isdigit()])
                    
                    # Scrape pages 2 to last_page
                    for page_num in range(2, last_page + 1):
                        page_url = f"{category_url}?page={page_num}"
                        logger.info(f"Scraping page {page_num} of {category}")
                        
                        page_soup = self._make_request(page_url)
                        if page_soup:
                            self._scrape_products_from_page(page_soup, menu_items, default_category=category)
                except Exception as e:
                    logger.warning(f"Error processing pagination for {category}: {str(e)}")
        
        # Remove duplicates based on name
        unique_items = []
        seen_names = set()
        
        for item in menu_items:
            if item["name"] not in seen_names:
                unique_items.append(item)
                seen_names.add(item["name"])
                
        logger.info(f"Scraped {len(unique_items)} unique menu items")
        return unique_items
    
    def _scrape_products_from_page(self, soup: BeautifulSoup, menu_items: List[Dict], default_category: str = None) -> None:
        """Extract product information from a page and add to menu_items list."""
        # Flurys website uses different product card structures, try all of them
        product_selectors = [
            '.grid__item', 
            '.product-item',
            '.product-card',
            '[class*="product"]'
        ]
        
        # Try all selectors until we find something
        products = []
        for selector in product_selectors:
            products = soup.select(selector)
            if products:
                break
                
        if not products:
            logger.warning("No products found on page")
            return
            
        for product in products:
            try:
                # Skip if this doesn't look like a product
                # Check for name and price elements
                name_element = product.select_one('h2, h3, h4, .product-title, .product-item__title, [class*="title"]')
                price_element = product.select_one('.price, [class*="price"]')
                
                if not name_element or not price_element:
                    continue
                
                name = name_element.text.strip()
                
                # Skip if no name or if it's a navigation element and not a product
                if not name or name in ["View All", "Shop Now", "BUY NOW"]:
                    continue
                
                # Extract price
                price_text = price_element.text.strip()
                price = 0.0
                
                # Extract numeric value with regex (handles ₹ 1,200.00 format)
                price_regex = r'₹\s*([\d,]+(?:\.\d+)?)'
                price_match = re.search(price_regex, price_text)
                if price_match:
                    price = float(price_match.group(1).replace(',', ''))
                
                # Extract description
                description = ""
                # Try different description selectors
                desc_selectors = [
                    '.product-description', 
                    '.description',
                    '.product-item__description',
                    'p'
                ]
                
                for selector in desc_selectors:
                    desc_element = product.select_one(selector)
                    if desc_element and desc_element.text.strip():
                        description = desc_element.text.strip()
                        break
                
                # Determine category
                category = default_category or "Other"
                
                # Try to infer category from product name or description if not specified
                if not default_category:
                    item_text = (name + " " + description).lower()
                    
                    if any(kw in item_text for kw in ['cake', 'pastry']):
                        category = "Cakes" if 'cake' in item_text else "Pastries"
                    elif any(kw in item_text for kw in ['bread', 'loaf', 'croissant']):
                        category = "Breads"
                    elif 'chocolate' in item_text:
                        category = "Chocolates"
                    elif any(kw in item_text for kw in ['cookie', 'biscuit']):
                        category = "Cookies"
                    elif 'brownie' in item_text:
                        category = "Brownies"
                    elif any(kw in item_text for kw in ['savour', 'patty', 'cheese']):
                        category = "Savouries"
                
                # Dietary information extraction
                dietary_info = {}
                
                # Check for allergens and dietary info in description
                item_text = (name + " " + description).lower()
                
                # Vegetarian check
                if 'vegetarian' in item_text:
                    dietary_info["vegetarian"] = True
                elif any(word in item_text for word in ['chicken', 'mutton', 'beef', 'pork', 'fish', 'meat']):
                    dietary_info["vegetarian"] = False
                    
                # Vegan check
                if 'vegan' in item_text:
                    dietary_info["vegan"] = True
                elif any(word in item_text for word in ['egg', 'milk', 'cream', 'butter', 'cheese']):
                    dietary_info["vegan"] = False
                    
                # Gluten-free check
                if 'gluten-free' in item_text or 'gluten free' in item_text:
                    dietary_info["gluten_free"] = True
                    
                # Allergen detection
                if "allergen" in item_text:
                    allergen_info = re.search(r'allergens?\s*[-:]\s*([^.]+)', item_text)
                    if allergen_info:
                        allergens = [a.strip() for a in allergen_info.group(1).split(',')]
                        
                        if any(a in ["gluten"] for a in allergens):
                            dietary_info["gluten_free"] = False
                            
                        if "egg" in allergens:
                            dietary_info["vegan"] = False
                            
                        if "milk" in allergens:
                            dietary_info["vegan"] = False
                
                # Eggless detection
                if 'eggless' in item_text:
                    # If it's explicitly eggless, it's likely vegetarian
                    dietary_info["vegetarian"] = True
                
                menu_items.append({
                    "name": name,
                    "description": description,
                    "price": price,
                    "category": category,
                    "dietary_info": dietary_info
                })
            except Exception as e:
                logger.warning(f"Error extracting menu item: {str(e)}")
    
    def scrape_special_features(self, url: str) -> Dict:
        """Scrape special features and dietary information."""
        soup = self._make_request(url)
        if not soup:
            logger.error(f"Failed to fetch {url}")
            return {}
        
        # Initialize with no features
        special_features = {}
        
        # Check page content for indicators of special features
        page_text = soup.get_text().lower()
        
        # Only include features if we find evidence for them on the page
        if "we deliver pan india" in page_text.lower():
            special_features["delivery"] = True
            special_features["takeout"] = True  # If they deliver, they likely do takeout
        
        if "takeout" in page_text or "take out" in page_text or "take-out" in page_text or "takeaway" in page_text:
            special_features["takeout"] = True
        
        if "reservation" in page_text or "book a table" in page_text or "book table" in page_text:
            special_features["reservations"] = True
        
        if "outdoor seating" in page_text or "outdoor dining" in page_text or "patio" in page_text:
            special_features["outdoor_seating"] = True
        
        if "wheelchair" in page_text or "accessibility" in page_text or "disabled access" in page_text:
            special_features["wheelchair_accessible"] = True
        
        if "parking" in page_text or "car park" in page_text or "valet" in page_text:
            special_features["parking"] = True
        
        if "free wifi" in page_text or "wi-fi" in page_text or "wifi available" in page_text:
            special_features["wifi"] = True
        
        if "happy hour" in page_text or "discount hours" in page_text:
            special_features["happy_hour"] = True
        
        if "live music" in page_text or "band" in page_text or "performance" in page_text:
            special_features["live_music"] = True
        
        if "kids" in page_text or "children" in page_text or "family friendly" in page_text:
            special_features["kids_friendly"] = True
        
        if "wine" in page_text or "liquor" in page_text or "alcohol" in page_text or "beer" in page_text or "cocktail" in page_text:
            special_features["alcohol_served"] = True
        
        # Add this for cafe detection
        if "tearoom" in page_text.lower() or "cafe" in page_text.lower():
            special_features["cafe"] = True
        
        return special_features
    
    def scrape_operating_hours(self, url: str) -> Dict:
        """Scrape operating hours and contact information."""
        soup = self._make_request(url)
        if not soup:
            logger.error(f"Failed to fetch {url}")
            return {}
        
        # Initialize with empty dictionary - no assumptions
        operating_hours = {}
        
        # Look for hours of operation in the page content
        try:
            # Find elements that might contain hours information
            hours_section = soup.find(string=re.compile(r'hours|timings|open|opening', re.I))
            if hours_section:
                parent_element = hours_section.parent
                if parent_element:
                    hours_text = parent_element.get_text()
                    
                    # Try to extract operating hours using regex patterns
                    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                    time_pattern = r'(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s*-\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm))'
                    
                    for day in days:
                        day_pattern = re.compile(f'{day}s?', re.I)
                        if day_pattern.search(hours_text):
                            day_section = hours_text[day_pattern.search(hours_text).start():]
                            time_match = re.search(time_pattern, day_section)
                            
                            if time_match:
                                open_time = time_match.group(1).strip()
                                close_time = time_match.group(2).strip()
                                
                                # Convert to 24-hour format
                                def convert_to_24h(time_str):
                                    time_str = time_str.lower()
                                    if 'am' in time_str or 'pm' in time_str:
                                        hour, minute = time_str.replace('am', '').replace('pm', '').strip().split(':') if ':' in time_str else (time_str.replace('am', '').replace('pm', '').strip(), '00')
                                        hour = int(hour)
                                        minute = int(minute)
                                        
                                        if 'pm' in time_str and hour < 12:
                                            hour += 12
                                        if 'am' in time_str and hour == 12:
                                            hour = 0
                                            
                                        return f"{hour:02d}:{minute:02d}"
                                    return time_str
                                
                                operating_hours[day] = {
                                    "open": convert_to_24h(open_time),
                                    "close": convert_to_24h(close_time)
                                }
        except Exception as e:
            logger.warning(f"Error extracting operating hours: {str(e)}")
        
        # Try to get operating hours from contact page
        contact_url = urljoin(url, '/pages/contact-us')
        contact_soup = self._make_request(contact_url)
        if contact_soup:
            hours_section = contact_soup.select_one('.store-hours, .hours')
            # Process hours if found
        
        # Don't return any default hours if none are found
        return operating_hours 