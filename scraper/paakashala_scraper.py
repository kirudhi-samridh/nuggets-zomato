import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup, Tag
from loguru import logger

from .base_scraper import BaseScraper
from knowledge_base.schema import RestaurantInfo, MenuItem, OperatingHours, SpecialFeatures # Import schema

class PaakashalaScraper(BaseScraper):
    """Scraper for Paakashala vegetarian restaurant chain website."""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.base_url = "https://paakashala.com/"
    
    # --- Helper to parse location divs ---
    def _parse_location_div(self, div: Tag) -> Optional[Dict]:
        location_data = {}
        try:
            name_elem = div.find('h2')
            location_data['name'] = name_elem.get_text().strip() if name_elem else 'Unknown Location'

            address_elem = div.find(string=re.compile(r"Bengaluru|Kundapura|Karnataka|Ananthpuram|Murudeshwara|Chitradurga")) # More robust address finding
            location_data['address'] = address_elem.strip() if address_elem else 'Address not found'

            phone_elem = div.find('a', href=lambda href: href and href.startswith('tel:'))
            if not phone_elem: # Fallback to text search if tel: link is missing
                 phone_text_elem = div.find(string=re.compile(r'\*?\s?\d{8,10}')) # Look for phone number pattern in text
                 if phone_text_elem:
                     phone_match = re.search(r'(\d{8,10})', phone_text_elem)
                     location_data['phone'] = phone_match.group(1) if phone_match else ''
                 else:
                     location_data['phone'] = ''
            else:
                 location_data['phone'] = phone_elem.get('href').replace('tel:', '').strip()


            rating_elem = div.find(string=re.compile(r'\d\.\d')) # Find text like '4.2'
            location_data['rating'] = float(rating_elem.strip()) if rating_elem else None

            reviews_elem = div.find(string=re.compile(r'\d+\+ Reviews')) # Find text like '5104+ Reviews'
            if reviews_elem:
                reviews_match = re.search(r'(\d+)\+', reviews_elem)
                location_data['reviews'] = int(reviews_match.group(1)) if reviews_match else None
            else:
                location_data['reviews'] = None

            # Find the 'Directions' link for the Google Maps URL
            directions_link = div.find('a', string='Directions')
            location_data['google_maps_url'] = directions_link['href'] if directions_link and directions_link.has_attr('href') else None

            return location_data
        except Exception as e:
            logger.error(f"Error parsing location div: {e}")
            return None

    # --- Scraper Methods ---

    def scrape_restaurant_info(self, url: str) -> RestaurantInfo:
        """Scrape basic restaurant information."""
        logger.info(f"Scraping restaurant info from {url}")
        
        soup = self._make_request(url)
        if not soup:
            # Return default structure on failure
             return RestaurantInfo(
                name="Paakashala",
                address="",
                phone="",
                email=None,
                website=self.base_url,
                cuisine=["Vegetarian"]
            )

        # Extract restaurant name (consistent)
        name = "Paakashala"

        # General contact info is not clearly available on homepage, try contact page
        # Use default empty strings if not found. Specific branches have phones.
        address = "" # General address not obvious
        phone = ""   # General phone not obvious
        email = None # General email not obvious

        contact_url = f"{self.base_url}contact-us" # Corrected URL
        contact_soup = self._make_request(contact_url)
        if contact_soup:
            try:
                # Attempt to find general email or phone if available on contact page
                email_elem = contact_soup.find('a', href=lambda href: href and href.startswith('mailto:'))
                if email_elem:
                    email = email_elem.get('href').replace('mailto:', '').strip()
                # Add similar logic for general phone/address if identifiable elements exist

                logger.info(f"Extracted general contact information if available - Email: {email}")
            except Exception as e:
                logger.error(f"Error extracting general contact information from {contact_url}: {str(e)}")


        # Extract cuisine types from homepage sections
        cuisine = []
        cuisine_sections = soup.find_all('h3', string=re.compile(r'(South Indian|North Indian|Chinese|Chaats)'))
        if cuisine_sections:
             cuisine = [h3.get_text().strip() for h3 in cuisine_sections]
        cuisine.append("Vegetarian") # Always add Vegetarian

        return RestaurantInfo(
            name=name,
            address=address, # Use branch address if needed, general one seems absent
            phone=phone,     # Use branch phone if needed, general one seems absent
            email=email,
            website=self.base_url, # Use base URL as the main website
            cuisine=list(set(cuisine)) # Ensure unique list
        )

    def scrape_menu(self, url: str) -> List[MenuItem]:
        """Scrape restaurant menu items from the dedicated menu page."""
        menu_page_url = f"{self.base_url}paakashala-menu/"
        logger.info(f"Scraping menu directly from {menu_page_url}")

        # Use the base URL provided in the function call as a fallback if needed,
        # but prioritize the dedicated menu page.
        # soup = self._make_request(url) # Keep original URL soup for potential fallbacks if needed later

        menu_soup = self._make_request(menu_page_url)
        if not menu_soup:
            logger.error(f"Failed to fetch menu page: {menu_page_url}")
            return []

        menu_items: List[MenuItem] = []

        # Target the content area of the "All" tab first (usually active by default)
        # Elementor structure: Look for containers holding the paired image and price list.
        # These containers seem to be direct children of the main tab content container.
        # Let's find the main content area first. The tab content divs have id="e-n-tab-content-XXXX"
        all_tab_content = menu_soup.find('div', id=re.compile(r"e-n-tab-content-\d+"), class_='e-active')
        if not all_tab_content:
             # Fallback: try finding the first tab content if no active class found
             all_tab_content = menu_soup.find('div', id=re.compile(r"e-n-tab-content-\d+"))
             if not all_tab_content:
                   logger.error("Could not find the main menu content container in the HTML.")
                   return []

        # Find all sections within the active tab content that represent a sub-category menu listing.
        # These seem to be 'e-con-full' containers based on the provided HTML.
        sub_category_sections = all_tab_content.find_all('div', class_='e-con-full', recursive=False) # Look for direct children containers
        if not sub_category_sections:
             # Refined search if direct children don't work
             sub_category_sections = all_tab_content.find_all('div', class_=re.compile(r'elementor-element-[\w]+ e-con-full'))
             logger.warning(f"Using refined search for sub-category sections. Found: {len(sub_category_sections)}")


        logger.info(f"Found {len(sub_category_sections)} potential sub-category sections.")

        for section in sub_category_sections:
            # Find the heading (sub-category name) within this section
            category_elem = section.find('h3', class_='elementor-heading-title')
            category = category_elem.get_text().strip() if category_elem else "Unknown Category"

            # Find the price list within this section
            price_list_ul = section.find('ul', class_='elementor-price-list')

            if price_list_ul:
                logger.debug(f"Processing category: {category}")
                items_in_category = price_list_ul.find_all('li', class_='elementor-price-list-item')
                logger.debug(f"Found {len(items_in_category)} items in {category}")

                for item_tag in items_in_category:
                    name = ""
                    description = ""
                    price = 0.0 # Price is not available in the HTML

                    name_elem = item_tag.find('span', class_='elementor-price-list-title')
                    if name_elem:
                        name = name_elem.get_text().strip()

                    desc_elem = item_tag.find('p', class_='elementor-price-list-description')
                    if desc_elem:
                        description = desc_elem.get_text().strip()

                    if name: # Only add item if a name was found
                        try:
                            menu_item = MenuItem(
                                name=name,
                                description=description,
                                price=price, # Set to 0.0 as it's missing
                                category=category, # Use the sub-category heading
                                dietary_info={
                                    "vegetarian": True, # Paakashala is vegetarian
                                    "vegan": "vegan" in description.lower(), # Basic check
                                    "gluten_free": "gluten free" in description.lower() or "gluten-free" in description.lower() # Basic check
                                }
                            )
                            menu_items.append(menu_item)
                        except Exception as item_e:
                            logger.warning(f"Could not create MenuItem for '{name}' in category '{category}': {item_e}")
                    else:
                        logger.warning(f"Skipping item in category '{category}' due to missing name. Tag: {item_tag}")
            # else:
                 # logger.warning(f"No price list found for category section: {category}")


        if not menu_items:
            logger.warning("No menu items were scraped dynamically from the menu page. Structure might have changed or page content is different.")

        logger.info(f"Scraped {len(menu_items)} menu items total from {menu_page_url}.")
        return menu_items

    def scrape_special_features(self, url: str) -> SpecialFeatures:
        """Scrape special features based on website content."""
        logger.info(f"Scraping special features from {url}")
        soup = self._make_request(url)
        features = SpecialFeatures() # Start with defaults from schema (all False)

        if soup:
             # Check for Catering (implies takeout/delivery potential)
             if soup.find(string=re.compile("Bespoke Vegetarian Catering", re.IGNORECASE)):
                 logger.info("Found 'Catering' information.")
                 features.takeout = True # Assume catering implies takeout capability
                 # Delivery might be part of catering, setting to True but may need verification
                 features.delivery = True

             # Check for Party Halls (implies reservations potential)
             if soup.find(string=re.compile("Elegant Party Halls", re.IGNORECASE)):
                  logger.info("Found 'Party Halls' information.")
                  features.reservations = True # Assume party halls require reservations

             # Parking - Check location details? Often mentioned per branch. This requires location scraping first.
             # Wifi, Outdoor Seating, Wheelchair Accessible - Not obvious from homepage. Defaulting to False.
             # Alcohol Served - Paakashala is likely pure veg, so False.
             features.alcohol_served = False
             # Kids Friendly - Often implied for family restaurants, but not explicitly stated. Default False.
             # Happy Hour, Live Music - Not mentioned. Default False.


        # Paakashala is vegetarian, confirmed by context. Schema handles dietary info per item.

        logger.info(f"Detected features: {features.dict()}")
        return features

    def scrape_operating_hours(self, url: str) -> Dict[str, OperatingHours]:
        """Scrape operating hours. Currently assumes not available generally."""
        # Operating hours are not clearly listed on the main page or contact page provided.
        # They might be per-location. Returning empty dict for now.
        # This could be enhanced if hours are found within location details or a dedicated page.
        logger.warning("General operating hours not found on main pages. Check individual locations if needed.")
        return {} # Return empty dict as per schema if no general hours found


    def scrape_locations(self, url: str) -> List[Dict]:
        """Scrape all branch locations from the website."""
        logger.info(f"Scraping locations from {url}")

        soup = self._make_request(url)
        if not soup:
            return []

        locations = []
        # Find the container holding the location cards
        # Based on the provided HTML snippet, location info seems structured.
        # Let's look for divs that contain address-like text and a 'Directions' link.
        # This is heuristic and might need adjustment based on the live site structure.

        # Option 1: Find a common parent section for locations
        location_section = soup.find('section', {'data-id': lambda x: x and 'locations' in x.lower()}) # Heuristic data-id
        if not location_section:
             # Option 2: Find divs containing a 'Directions' link, likely candidates for location blocks
             direction_links = soup.find_all('a', string='Directions')
             potential_location_divs = [link.find_parent('div', class_=lambda x: x and 'elementor-widget-wrap' in x) for link in direction_links] # Look for a common wrapper div
             # Filter out None results if find_parent fails
             potential_location_divs = [div for div in potential_location_divs if div]
        else:
            potential_location_divs = location_section.find_all('div', class_=lambda x: x and 'elementor-widget-wrap' in x) # Find wrappers within the section


        logger.info(f"Found {len(potential_location_divs)} potential location divs.")

        parsed_locations_count = 0
        unique_addresses = set() # To avoid duplicates if parsing catches overlapping divs

        for div in potential_location_divs:
             location_data = self._parse_location_div(div)
             if location_data and location_data.get('address') != 'Address not found':
                 # Check for duplicates based on address before adding
                 if location_data['address'] not in unique_addresses:
                     locations.append(location_data)
                     unique_addresses.add(location_data['address'])
                     parsed_locations_count += 1
                 # else:
                     # logger.debug(f"Skipping duplicate location based on address: {location_data['address']}")


        # Fallback or alternative: Check the footer list if main content fails
        if not locations:
             logger.info("Primary location scraping failed or yielded no results. Trying footer list.")
             footer_locations_list = soup.find('h2', string='Locations')
             if footer_locations_list:
                  footer_ul = footer_locations_list.find_next_sibling('ul')
                  if footer_ul:
                      footer_lis = footer_ul.find_all('li')
                      for li in footer_lis:
                           name = li.get_text().strip()
                           # Limited info from footer, add basic entry
                           if name not in unique_addresses: # Use name as proxy for uniqueness here
                               locations.append({
                                   "name": name,
                                   "address": "See website for details", # Placeholder
                                   "phone": "",
                                   "rating": None,
                                   "reviews": None,
                                   "google_maps_url": None
                               })
                               unique_addresses.add(name)
                               parsed_locations_count += 1


        logger.info(f"Successfully parsed {parsed_locations_count} unique locations.")
        if not locations:
             logger.warning("Could not scrape any locations.")

        return locations

# Example usage (optional, for testing)
# if __name__ == '__main__':
#     config = {"retries": 3, "delay": 1}
#     scraper = PaakashalaScraper(config)
#     base_url = "https://paakashala.com/"
#
#     print("--- Scraping Restaurant Info ---")
#     info = scraper.scrape_restaurant_info(base_url)
#     print(info)
#
#     print("\n--- Scraping Menu Items ---")
#     menu = scraper.scrape_menu(base_url)
#     # print(f"Found {len(menu)} items. First 5:")
#     # for item in menu[:5]:
#     #     print(item)
#
#     print("\n--- Scraping Special Features ---")
#     features = scraper.scrape_special_features(base_url)
#     print(features)
#
#     print("\n--- Scraping Operating Hours ---")
#     hours = scraper.scrape_operating_hours(base_url)
#     print(hours)
#
#     print("\n--- Scraping Locations ---")
#     locations = scraper.scrape_locations(base_url)
#     print(f"Found {len(locations)} locations:")
#     # for loc in locations:
#     #     print(loc) 