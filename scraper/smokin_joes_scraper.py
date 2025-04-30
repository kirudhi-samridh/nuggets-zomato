import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup, Tag
from loguru import logger

from .base_scraper import BaseScraper

class SmokinJoesScraper(BaseScraper):
    """Scraper for Smokin' Joe's Pizza website (smokinjoespizza.com)."""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.base_url = "https://www.smokinjoespizza.com/"
    
    def scrape_restaurant_info(self, url: str) -> Dict:
        """Scrape basic restaurant information."""
        logger.info(f"Scraping restaurant info from {url}")
        
        soup = self._make_request(url)
        if not soup:
            logger.warning(f"Failed to fetch main page {url}")
            return {}
        
        # --- Extract Name ---
        name = "Smokin' Joe's Pizza" # Default, try to refine
        try:
            # Try footer copyright
            footer_text = soup.find(text=re.compile(r"© Copyrights \d{4} Smokin' Joe's Pizza", re.IGNORECASE))
            if footer_text:
                match = re.search(r"Smokin' Joe's Pizza", str(footer_text), re.IGNORECASE)
                if match:
                    name = match.group(0).strip()
            else:
                # Try title tag
                title_tag = soup.find('title')
                if title_tag and "Smokin' Joe's" in title_tag.get_text():
                    name = "Smokin' Joe's Pizza" 
                else:
                    logger.warning("Could not reliably determine restaurant name, using default.")
        except Exception as e:
            logger.warning(f"Error extracting restaurant name: {e}")

        # --- Extract Contact Info (from Contact Us page) ---
        contact_url = self._construct_url("contact-us")
        contact_soup = self._make_request(contact_url)
        
        address = ""
        phone = ""
        email = ""
        
        if contact_soup:
            try:
                # Look for common contact patterns or specific elements
                # This part is highly dependent on the actual structure of contact-us page
                
                # Attempt 1: Find elements with contact-related classes/ids
                contact_section = contact_soup.find(['div', 'section'], class_=re.compile(r'contact', re.IGNORECASE)) or contact_soup
                
                # Extract Address (Look for keyword 'Address' or typical address elements)
                address_elem = contact_section.find(text=re.compile(r'Address', re.IGNORECASE))
                if address_elem:
                     # Try finding the address in the parent or siblings
                     parent = address_elem.find_parent(['p', 'div', 'li'])
                     if parent:
                         address = parent.get_text(separator=' ', strip=True).replace("Address", "").strip(": ")
                 
                if not address:
                     # Fallback regex on the section text
                     address_match = re.search(r'Address[:\s]+(.*?)(?=Phone|Email|\n{2,})', contact_section.get_text(separator=' ', strip=True), re.IGNORECASE | re.DOTALL)
                     if address_match:
                         address = address_match.group(1).strip()

                # Extract Phone (Look for 'tel:' links or phone patterns)
                phone_link = contact_section.find('a', href=re.compile(r'tel:'))
                if phone_link:
                    phone = phone_link['href'].replace('tel:', '').strip()
                
                if not phone:
                    # Fallback regex
                    phone_match = re.search(r'Phone[:\s]+(\+?[\d\s\-\(\)]{7,})', contact_section.get_text(separator=' ', strip=True), re.IGNORECASE)
                    if phone_match:
                        phone = phone_match.group(1).strip()

                # Extract Email (Look for 'mailto:' links or email patterns)
                email_link = contact_section.find('a', href=re.compile(r'mailto:'))
                if email_link:
                    email = email_link['href'].replace('mailto:', '').strip()
                
                if not email:
                     # Fallback regex
                     email_match = re.search(r'Email[:\s]+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', contact_section.get_text(separator=' ', strip=True), re.IGNORECASE)
                     if email_match:
                         email = email_match.group(1).strip()

                if not address: logger.warning(f"Could not extract address from {contact_url}")
                if not phone: logger.warning(f"Could not extract phone number from {contact_url}")
                if not email: logger.warning(f"Could not extract email from {contact_url}")

            except Exception as e:
                logger.error(f"Error parsing contact information from {contact_url}: {e}")
        else:
            logger.warning(f"Failed to fetch contact page {contact_url}")

        # --- Extract Website ---
        website = url # Use the provided URL as the website

        # --- Extract Cuisine ---
        # Primarily pizza based on the name and content
        cuisine = ["Pizza"]
        # Could add more based on menu analysis if needed, e.g., Italian, Fast Food
        if soup.find(text=re.compile(r'Pizza Sandwiches|Garlic Breads|Pasta', re.IGNORECASE)):
                cuisine.append("Italian")
                cuisine.append("Fast Food")
        cuisine = list(set(cuisine)) # Ensure uniqueness
        
        return {
            "name": name,
            "address": address,
            "phone": self._clean_phone(phone),
            "email": email,
            "website": website,
            "cuisine": cuisine
        }
    
    def scrape_menu(self, url: str) -> List[Dict]:
        """Scrape menu items from main page and linked category pages."""
        logger.info(f"Scraping menu from main page {url} and linked category pages.")
        
        main_soup = self._make_request(url)
        if not main_soup:
             logger.warning(f"Failed to fetch main menu page {url}. Cannot proceed with menu scraping.")
             return []
        
        menu_items = []
        scraped_item_names = set() # To avoid duplicates if item appears in multiple places

        # --- Scrape Top Selling Pizzas (from main page) ---
        try:
            pizza_container = main_soup.find('div', id="top-selling-pizzas")
            if pizza_container:
                pizza_elements = pizza_container.find_all(lambda tag: tag.name == 'div' and 'item' in tag.get('class', []), recursive=False)
                if not pizza_elements: pizza_elements = pizza_container.find_all('div', class_=re.compile(r'item'))
                logger.info(f"Found {len(pizza_elements)} potential top selling pizza elements on main page.")
                
                for item_div in pizza_elements:
                    self._extract_menu_item_card(item_div, "Pizza", menu_items, scraped_item_names)
            else:
                 logger.warning("Could not find container div#top-selling-pizzas on main page.")
        except Exception as e:
             logger.error(f"Error scraping top selling pizzas from main page: {e}", exc_info=True)

        # --- Scrape Weekly Specials (from main page) ---
        try:
            specials_list = main_soup.select_one('div.slide6 div.pizza-day-chart ul')
            if specials_list:
                 specials_li = specials_list.find_all('li', recursive=False)
                 logger.info(f"Found {len(specials_li)} potential weekly special elements on main page.")
                 for li in specials_li:
                      spans = li.find_all('span')
                      if len(spans) == 2:
                           day = spans[0].get_text(strip=True).replace(':','').strip()
                           special_name = spans[1].get_text(strip=True)
                           if day and special_name:
                                item_name = f"{day} Special: {special_name}"
                                if item_name not in scraped_item_names:
                                     is_veg = not any(non_veg in special_name.lower() for non_veg in ['chicken', 'meat'])
                                     menu_items.append({
                                         "name": item_name,
                                         "description": f"Special offer for {day}",
                                         "price": 0.0, # Price not listed
                                         "category": "Special Offers",
                                         "dietary_info": {"vegetarian": is_veg, "vegan": False, "gluten_free": False}
                                     })
                                     scraped_item_names.add(item_name)
                                else:
                                     logger.debug(f"Skipping duplicate special item: {item_name}")
                           else: logger.warning(f"Could not extract day/special from li: {li.get_text(strip=True)}")
                      else: logger.warning(f"Skipping special li, expected 2 spans, found {len(spans)}: {li.get_text(strip=True)}")
            else:
                logger.warning("Weekly specials list (div.slide6 div.pizza-day-chart ul) not found on main page.")
        except Exception as e:
            logger.error(f"Error scraping weekly specials from main page: {e}", exc_info=True)

        # --- Find and Scrape Category Pages ---
        processed_categories = set(["Pizza", "Special Offers"]) # Keep track of categories processed
        try:
             category_links = main_soup.select('div.recipe-categories a.recipe-category')
             logger.info(f"Found {len(category_links)} category links to potentially scrape.")
             
             for link in category_links:
                  href = link.get('href')
                  category_name_from_link = link.find('div', class_='recipe-category-info')
                  category_name = category_name_from_link.get_text(strip=True) if category_name_from_link else "Unknown Category"
                  
                  # Skip if it's the main pizza page again or an invalid link
                  if not href or href == 'pizza.html' or href == '#': 
                       logger.debug(f"Skipping category link: {category_name} (href: {href})")
                       continue
                  
                  # Skip if category seems already covered (e.g., Top Selling Pizzas)
                  if category_name in processed_categories:
                       logger.debug(f"Skipping already processed category: {category_name}")
                       continue

                  category_url = self._construct_url(href)
                  logger.info(f"--- Scraping category page: {category_name} ({category_url}) ---")
                  category_soup = self._make_request(category_url)
                  
                  if category_soup:
                       # Try to determine a more specific category name from the page title or h1/h2
                       page_title = category_soup.find('title')
                       page_header = category_soup.find(['h1', 'h2'])
                       if page_header: category_name = page_header.get_text(strip=True)
                       elif page_title: category_name = page_title.get_text().split('|')[0].strip() # Use title as fallback
                       
                       processed_categories.add(category_name) # Mark as processed
                       
                       # Find item containers (assuming similar structure to main page: divs with class 'item' or 'card')
                       # This might need adjustment per category page
                       item_containers = category_soup.select('div.item, div.card') # Broad selection, refine if needed
                       if not item_containers:
                            # Fallback: Look for rows containing columns often used for items
                            item_containers = category_soup.select('div.row > div[class*="col-"]') 
                            
                       logger.info(f"Found {len(item_containers)} potential item containers on {category_name} page.")
                       
                       items_added_from_page = 0
                       for item_div in item_containers:
                           # Reuse the card extraction logic
                           if self._extract_menu_item_card(item_div, category_name, menu_items, scraped_item_names):
                                items_added_from_page += 1
                                
                       logger.info(f"Added {items_added_from_page} new items from category: {category_name}")
                  else:
                       logger.warning(f"Failed to fetch category page: {category_url}")
        except Exception as e:
             logger.error(f"Error occurred while finding/scraping category pages: {e}", exc_info=True)

        logger.info(f"Finished menu scraping. Total items found: {len(menu_items)}")
        return menu_items

    def _extract_menu_item_card(self, item_container: Tag, category: str, menu_list: List[Dict], scraped_names: set) -> bool:
        """Helper to extract item details from a card-like structure. Adds item with price 0.0 if parsing fails."""
        card = item_container if 'card' in item_container.get('class', []) else item_container.find('div', class_='card')
        name_elem = None
        price_size_elem = None
        is_veg = False # Default to False unless proven otherwise
        
        if not card:
            # If no card, check if the container itself has name/price (less structured pages)
            name_elem = item_container.find(['h3', 'h4']) # More flexible name finding
            # Try finding specific price/size class first, then broader text match
            price_size_elem = item_container.find(['h5', 'p', 'div'], class_=lambda x: x and ('price' in x or 'size' in x))
            if not price_size_elem:
                 price_elem_text = item_container.find(text=re.compile(r'₹|Rs\.'))
                 # If text match, find a reasonable parent element containing it
                 if price_elem_text: 
                      # Ensure we get a tag, not just NavigableString, to check name later
                      parent_tag = price_elem_text.find_parent(['h5', 'p', 'div'])
                      price_size_elem = parent_tag if parent_tag else price_elem_text # Use parent if found
                     
            if not name_elem or not price_size_elem: 
                return False # Cannot extract essential info
            container_classes = item_container.get('class', [])
            is_veg = 'veg' in container_classes and 'non-veg' not in container_classes
        else:
            # Standard card structure
            name_elem = card.find('h3', class_='card-title')
            price_size_elem = card.find('h5', class_='size')
            card_classes = card.get('class', [])
            is_veg = 'veg' in card_classes and 'non-veg' not in card_classes

        if not isinstance(price_size_elem, Tag):
             if hasattr(price_size_elem, 'find_parent'):
                  parent = price_size_elem.find_parent(['h5', 'p', 'div'])
                  if parent:
                       price_size_elem = parent
                  else:
                       logger.warning(f"Price element was text node with no suitable parent tag for item: {name_elem.get_text(strip=True) if name_elem else 'N/A'}")
                       return False
             else:
                  logger.warning(f"Price element is not a Tag and has no parent for item: {name_elem.get_text(strip=True) if name_elem else 'N/A'}")
                  return False

        if name_elem and price_size_elem:
            name = name_elem.get_text(strip=True)
            if not name: return False 
            
            description_elem = name_elem.find_next_sibling('p')
            description = description_elem.get_text(strip=True) if description_elem else ""
            
            items_added = False
            processed_h5_size = False
            # Determine veg status early
            current_is_veg = is_veg or not any(nveg in name.lower() for nveg in ['chicken', 'meat', 'lamb', 'pepperoni', 'salami', 'bacon', 'prawn'])

            # Case 1: Try processing as h5.size structure first
            if price_size_elem.name == 'h5' and price_size_elem.has_attr('class') and 'size' in price_size_elem['class']:
                processed_h5_size = True
                price_spans = price_size_elem.find_all('span')
                if price_spans:
                    for span in price_spans:
                        span_text = span.get_text(strip=True)
                        match = re.search(r'(Regular|Medium|Large|MAHA)\D*?(\d+)', span_text, re.IGNORECASE)
                        if match:
                            size, price_str = match.groups()
                            try:
                                price = float(price_str)
                                item_name = f"{name} ({size.title()})"
                                if item_name not in scraped_names:
                                    menu_list.append({
                                        "name": item_name,
                                        "description": description if description else f"{size.title()} size of {name}",
                                        "price": price,
                                        "category": category,
                                        "dietary_info": {"vegetarian": current_is_veg, "vegan": False, "gluten_free": False}
                                    })
                                    scraped_names.add(item_name)
                                    items_added = True
                            except ValueError:
                                logger.warning(f"Could not convert price '{price_str}' to float for item '{name}' size '{size.title()}'")
                        # else: # No match in this span
                             # logger.debug(f"Regex did not match span text: '{span_text}' for item '{name}'")
                    # Log if spans existed but none resulted in adding items
                    if not items_added:
                         logger.warning(f"Found h5.size for \'{name}\' but failed to parse price/size from spans: {[s.get_text(strip=True) for s in price_spans]}")
                else:
                     logger.warning(f"Found h5.size for \'{name}\' but it contains no spans. Will attempt single price extraction.")
                     
            # Case 2: Attempt to extract a single price IF items weren't added via h5.size spans
            if not items_added:
                 price_text = price_size_elem.get_text(strip=True)
                 price_match = re.search(r'(?:₹|Rs\.?)\s*(\d+(?:\.\d+)?)', price_text)
                 item_name = name # Assume single item name
                 price = 0.0 # Default price if parsing fails
                 price_found = False
                 
                 if price_match:
                     try:
                         price = float(price_match.group(1))
                         price_found = True
                     except ValueError:
                         logger.warning(f"Regex matched price '{price_match.group(1)}' but failed to convert to float for item: '{name}'")
                 # else: # No regex match for single price
                      # Only log warning if we didn't already log about failed span parsing
                      # if not processed_h5_size:
                      #     logger.warning(f"Could not parse single price for item: '{name}' from element text: '{price_text[:100]}...'")
                 
                 # **Add the item even if price parsing failed (using default price 0.0)**
                 if item_name not in scraped_names:
                     if not price_found:
                         logger.warning(f"Could not parse price for item '{item_name}'. Adding with price 0.0.")
                     
                     menu_list.append({
                         "name": item_name,
                         "description": description if description else name,
                         "price": price, # Use extracted price or the default 0.0
                         "category": category,
                         "dietary_info": {"vegetarian": current_is_veg, "vegan": False, "gluten_free": False}
                     })
                     scraped_names.add(item_name)
                     items_added = True # Mark as added, even with default price
                 # else: # Item name (single version) already exists
                       # logger.debug(f"Skipping duplicate single item: {item_name}")
            
            return items_added # Return True if any item (size variant or single, with or without price) was added
                 
        return False # Name or price element missing initially
    
    def scrape_special_features(self, url: str) -> Dict:
        """Scrape special features based on website content."""
        logger.info(f"Scraping special features from {url}")
        
        soup = self._make_request(url)
        if not soup:
            logger.warning(f"Failed to fetch page {url} for special features.")
            return {}
        
        features = {
            "delivery": False,
            "takeout": False,
            "reservations": False,
            "outdoor_seating": False,
            "wheelchair_accessible": False,
            "parking": False,
            "wifi": False,
            "happy_hour": False, # Using for 'offers'
            "live_music": False,
            "kids_friendly": False,
            "alcohol_served": False
        }
        
        page_text = soup.get_text(' ', strip=True).lower() # Use space separator
        
        try:
            # Delivery / Order Online
            if soup.find('a', text=re.compile('Order Online', re.IGNORECASE)) or \
               re.search(r'order online|home delivery', page_text):
                features["delivery"] = True
        
            # Takeout (Often implied for pizza places, but check for keywords)
            if re.search(r'takeout|take[- ]?away|pick[- ]?up', page_text):
                features["takeout"] = True
            elif features["delivery"]: # Often if delivery, takeout is also possible
                features["takeout"] = True
                logger.info("Takeout inferred from delivery availability.")
        
            # Reservations (Check for booking links/text)
            if soup.find('a', text=re.compile('book|reservation', re.IGNORECASE)) or \
               re.search(r'reservation|book a table', page_text):
                features["reservations"] = True
        
            # Kids Friendly (Look for 'Maha Pizza', 'Family', or specific kids menus)
            if re.search(r'maha pizza|family|kids', page_text) or \
               soup.find(text=re.compile(r'Kids Menu', re.IGNORECASE)): # Add check for Kids menu section
                features["kids_friendly"] = True
        
            # Offers / Happy Hour (Look for 'Offers', 'Specials' sections/links)
            if soup.find('a', text=re.compile('Offers|Special', re.IGNORECASE)) or \
               re.search(r'offers|special', page_text):
                 features["happy_hour"] = True # Mapping 'offers' to 'happy_hour'

            # Alcohol (Check menu categories like Beverages, or explicit mentions)
            # Note: The provided sample shows 'Beers', 'Wines' etc. Out of Stock, but implies they *could* serve it.
            # A more robust check would be needed on the live menu page if structure changes.
            if soup.find(text=re.compile(r'Beer|Wine|Alcohol|Liquor|Cocktail', re.IGNORECASE)):
                 features["alcohol_served"] = True # Set to True if mentioned, even if currently out of stock
            
            # Other features (Parking, Wifi, etc.) are harder to determine reliably without explicit mentions.
            if not features["reservations"]: logger.info("Reservations feature not found.")
            if not features["outdoor_seating"]: logger.info("Outdoor Seating feature not found.")
            if not features["wheelchair_accessible"]: logger.info("Wheelchair Accessible feature not found.")
            if not features["parking"]: logger.info("Parking feature not found.")
            if not features["wifi"]: logger.info("Wifi feature not found.")
            if not features["live_music"]: logger.info("Live Music feature not found.")
            if not features["alcohol_served"]: logger.info("Alcohol Served feature not found/confirmed.")

        except Exception as e:
            logger.error(f"Error scraping special features: {e}")
        
        return features
    
    def scrape_operating_hours(self, url: str) -> Dict:
        """Scrape operating hours. Tries main page footer and contact page."""
        logger.info(f"Attempting to scrape operating hours from {url} and contact page.")
        
        hours_found = False
        operating_hours = {}
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        # Sources to check
        soups_to_check = []
        main_soup = self._make_request(url)
        if main_soup:
            soups_to_check.append(main_soup)
        else:
             logger.warning(f"Failed to fetch main page {url} for operating hours.")

        contact_url = self._construct_url("contact-us")
        contact_soup = self._make_request(contact_url)
        if contact_soup:
            soups_to_check.append(contact_soup)
        else:
            logger.warning(f"Failed to fetch contact page {contact_url} for operating hours.")

        if not soups_to_check:
             logger.warning("No pages available to check for operating hours.")
             return {}

        # Regex patterns to find hours
        # Example: Monday: 11:00 AM - 10:00 PM | Mon-Fri 11am to 11pm
        hour_pattern_day = re.compile(fr'(?:{ "|".join(days) }|Mon|Tue|Wed|Thu|Fri|Sat|Sun)[:\s]+(\d{{1,2}}(?::\d{{2}})?(?:\s*am|\s*pm)?)\s*(?:-|–|—|to)\s*(\d{{1,2}}(?::\d{{2}})?(?:\s*am|\s*pm)?)', re.IGNORECASE)
        hour_pattern_range = re.compile(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[\s-]+(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[:\s]+(\d{1,2}(?::\d{2})?(?:\s*am|\s*pm)?)\s*(?:-|–|—|to)\s*(\d{1,2}(?::\d{2})?(?:\s*am|\s*pm)?)', re.IGNORECASE)
        
        day_map = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}
        full_day_map = {day: day for day in days}
        full_day_map.update(day_map) # Combine for lookup

        for soup in soups_to_check:
            if hours_found:
                break # Stop if found in one source
            text_content = soup.get_text('\n') # Use newline separator for better pattern matching
            try:
                # Check for day ranges first
                for match in hour_pattern_range.finditer(text_content):
                    hours_found = True
                    start_day_abbr, end_day_abbr, open_time_str, close_time_str = match.groups()
                    start_day = full_day_map.get(start_day_abbr.title())
                    end_day = full_day_map.get(end_day_abbr.title())
                     
                    if start_day and end_day:
                        open_time = self._standardize_time(open_time_str)
                        close_time = self._standardize_time(close_time_str)
                        if open_time and close_time:
                            start_idx = days.index(start_day)
                            end_idx = days.index(end_day)
                               # Handle ranges that wrap around Sunday->Monday if needed (e.g. Sat-Mon)
                            current_idx = start_idx
                            while True:
                                day = days[current_idx]
                                if day not in operating_hours: # Avoid overwriting more specific single day entries
                                   operating_hours[day] = {"open": open_time, "close": close_time}
                                if current_idx == end_idx: 
                                    break
                                current_idx = (current_idx + 1) % 7
                        else:
                            logger.warning(f"Could not standardize time for range {start_day_abbr}-{end_day_abbr}: {open_time_str}-{close_time_str}")

                # Check for single day entries (potentially overwriting ranges if more specific)
                for match in hour_pattern_day.finditer(text_content):
                    hours_found = True
                    day_abbr, open_time_str, close_time_str = match.groups()
                    day = full_day_map.get(day_abbr.title())
                     
                    if day:
                        open_time = self._standardize_time(open_time_str)
                        close_time = self._standardize_time(close_time_str)
                        if open_time and close_time:
                            operating_hours[day] = {"open": open_time, "close": close_time}
                        else:
                            logger.warning(f"Could not standardize time for day {day_abbr}: {open_time_str}-{close_time_str}")
            except Exception as e:
                logger.error(f"Error parsing operating hours: {e}")

        if not hours_found:
            logger.warning("Operating hours not found on website (main page or contact page).")
            return {} # Return empty dict if no hours found
            
        # Fill missing days if some were found (e.g., if only Mon-Fri was specified)
        # This is an assumption - comment out if strict adherence to only found data is needed
        # all_days_present = all(day in operating_hours for day in days)
        # if hours_found and not all_days_present:
        #      logger.warning("Operating hours found but potentially incomplete for all days.")
            
        return operating_hours
    
    def scrape_locations(self, url: str) -> List[Dict]:
        """Scrape location information from the main page's Store Locator section."""
        logger.info(f"Scraping locations from {url}")
        
        soup = self._make_request(url)
        if not soup:
            logger.warning(f"Failed to fetch page {url} for locations.")
            return []
        
        locations = []
        
        try:
            # Find the "Store Locator" header
            locator_header = soup.find(['h2', 'h3'], text=re.compile('Store Locator', re.IGNORECASE))
            
            if locator_header:
                # Find the container (div/section) that likely holds the location list
                # This assumes the list follows the header, might need adjustment
                location_container = locator_header.find_next_sibling(['div', 'section'])
                if not location_container:
                     parent = locator_header.find_parent()
                     if parent: location_container = parent.find_next_sibling(['div', 'section']) # Try parent's sibling

                if location_container:
                    # Find potential location elements (e.g., links or divs containing city names)
                    # Based on sample: links like <a href=...> <city> </a>
                    location_elements = location_container.find_all('a') 
                    if not location_elements: # Fallback: try divs inside
                         location_elements = location_container.find_all('div')

                    for elem in location_elements:
                        city_text = elem.get_text(strip=True)
                         # Filter out non-city text if necessary
                        known_cities = ["Mumbai", "Navi Mumbai", "Pune", "Thane", "Lonavala", "Nashik", "Aurangabad", "Latur", "Goa", "Srinagar"]
                         
                        found_city = None
                        for known_city in known_cities:
                            if known_city.lower() in city_text.lower():
                                found_city = known_city
                                break
                         
                        if found_city:
                            state = "Maharashtra" # Default
                            if found_city == "Goa":
                                state = "Goa"
                            elif found_city == "Srinagar":
                                state = "Jammu and Kashmir"
                        
                             # Address is not detailed in this section
                            address = f"{found_city}, {state}, India"
                            logger.debug(f"Found location: {found_city}")
                        locations.append({
                                 "city": found_city,
                            "state": state,
                            "address": address
                        })
                         # else: # Log elements that might be locations but didn't match known cities
                             # logger.debug(f"Skipping potential location element, text: '{city_text[:50]}...'")
                else:
                    logger.warning("Could not find the container element after 'Store Locator' header.")
            else:
                 logger.warning("'Store Locator' header not found on the page.")
                 
        except Exception as e:
            logger.error(f"Error scraping locations: {e}")

        if not locations:
             logger.warning("No locations extracted from the Store Locator section.")
             # Option: could try scraping the dedicated /locations page if it exists and Store Locator fails
             # locations_url = self._construct_url("locations") 
             # ... attempt scraping locations_url ...
             
        return locations 

    def _construct_url(self, path: str) -> str:
        """Helper to construct absolute URLs."""
        if path.startswith(('http://', 'https://')):
            return path
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _standardize_time(self, time_str: str) -> Optional[str]:
        """Convert time strings (e.g., '9am', '10:30 PM') to HH:MM format."""
        if not time_str: return None
        try:
            time_str = time_str.strip().lower()
            is_pm = 'pm' in time_str
            is_am = 'am' in time_str
            
            time_str = time_str.replace('am', '').replace('pm', '').strip()
            
            parts = time_str.split(':')
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
            
            if hours < 0 or hours > 23 or minutes < 0 or minutes > 59: # Basic validation before AM/PM
                 if hours == 12 and (is_am or is_pm): # Allow 12 AM/PM
                      pass
                 else:
                     raise ValueError("Hours or minutes out of range")

            if is_pm and hours < 12:
                hours += 12
            elif is_am and hours == 12: # Handle 12 AM (midnight)
                hours = 0
            elif not is_am and not is_pm and hours < 9: # Heuristic: assume times like 1, 2, 7 are PM if no indicator
                 hours += 12
                 
            # Handle potential 24:00 case if scraper outputs it, map to 23:59 or 00:00 depending on context
            if hours == 24: hours = 0 # Treat 24:00 as 00:00 of next day

            return f"{hours:02d}:{minutes:02d}"
        except (ValueError, IndexError) as e:
            logger.warning(f"Could not parse time string: '{time_str}'. Error: {e}")
            return None
            
    def _clean_phone(self, phone_str: str) -> str:
        """Clean up extracted phone number string."""
        if not phone_str: return ""
        # Remove non-digit characters except leading +
        cleaned = re.sub(r'[^\d+]', '', phone_str)
        # Basic validation (e.g., minimum length)
        if len(re.sub(r'^\+', '', cleaned)) < 7:
             logger.warning(f"Potentially invalid phone number extracted: {phone_str}")
             return phone_str # Return original if cleaning seems to break it
        return cleaned

    # Override the main scrape method if needed, or rely on BaseScraper's implementation
    # def scrape(self, url: str) -> Dict:
    #     ... call the individual scrape_ methods ...
    #     return combined_data

# Example usage (for testing)
# if __name__ == '__main__':
#     import json
#     scraper = SmokinJoesScraper({})
#     data = scraper.scrape('https://www.smokinjoespizza.com/')
#     print(json.dumps(data, indent=2)) 