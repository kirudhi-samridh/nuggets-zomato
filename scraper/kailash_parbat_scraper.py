import re
import json
import io # Added for PDF parsing
import requests # Added for downloading PDF
from urllib.parse import urljoin # Added for handling relative PDF URLs
from typing import Dict, List, Optional
from bs4 import BeautifulSoup, Tag
from loguru import logger

# --- PDF/OCR Imports ---
try:
    from pdf2image import convert_from_bytes
    from PIL import Image # Pillow for image handling
except ImportError:
    logger.error("pdf2image or Pillow not installed. Please install them: poetry add pdf2image Pillow")
    convert_from_bytes = None
    Image = None

try:
    import pytesseract
except ImportError:
    logger.error("pytesseract not installed. Please install it: poetry add pytesseract")
    pytesseract = None
except FileNotFoundError: # Handle case where tesseract executable is not found
    logger.error("Tesseract executable not found. Make sure Tesseract is installed and in your PATH, or set the path in the script.")
    # Setting pytesseract to None will prevent OCR attempts
    pytesseract = None

# Import schema components for type hinting and structure
from knowledge_base.schema import RestaurantInfo, MenuItem, OperatingHours, SpecialFeatures

from .base_scraper import BaseScraper

class KailashParbatScraper(BaseScraper):
    """Scraper for Kailash Parbat restaurant."""

    def __init__(self, config: Dict):
        super().__init__(config)
        # Base URL not strictly needed for this static example but good practice
        self.base_url = "https://www.kailashparbatgroup.com/"

    def scrape_restaurant_info(self, url: str) -> Dict:
        """Scrape basic restaurant information conforming to RestaurantInfo schema."""
        logger.info(f"Scraping restaurant info from {url}")
        soup = self._make_request(url)
        if not soup:
            # Return structure with defaults matching schema non-optional fields
            return RestaurantInfo(
                name="Kailash Parbat (Unavailable)",
                address="Not Available",
                phone="Not Available",
                website=url
            ).dict()

        # Initialize with defaults for required fields
        info_data = {
            "name": "Kailash Parbat", # Hardcoded based on site content
            "description": None, # Description not directly in RestaurantInfo schema
            "cuisine": [],
            "website": url,
            "phone": "Not Available",
            "email": None,
            "address": "Not Available"
        }

        # Extract description (will be used for cuisine)
        legend_section = soup.find(lambda tag: tag.name == "h4" and "The Legend of Kailash Parbat" in tag.get_text())
        description_text = None
        if legend_section:
            description_p = legend_section.find_next_sibling("p")
            if description_p:
                description_text = description_p.get_text(strip=True)
                # info_data["description"] = description_text # Store if needed elsewhere, not in schema

        # Infer cuisine from description
        if description_text:
            desc_lower = description_text.lower()
            if "north indian" in desc_lower:
                info_data["cuisine"].append("North Indian")
            if "sindhi" in desc_lower:
                info_data["cuisine"].append("Sindhi")
            # Vegetarian info handled in menu items / special features

        if not info_data["cuisine"]:
             info_data["cuisine"].append("Indian") # Default guess

        # Extract Head Office address and email
        head_office_section = soup.find(lambda tag: tag.name == "h4" and "Head Office" in tag.get_text())
        if head_office_section:
            address_div = head_office_section.find_next_sibling("div")
            if address_div:
                # Get text, split by newline, strip whitespace, filter empty lines
                address_lines = [line.strip() for line in address_div.get_text(separator="\n").split("\n") if line.strip()]
                # Combine first 2 lines for address (heuristic)
                if len(address_lines) >= 2:
                    info_data["address"] = " ".join(address_lines[:2])
                elif address_lines:
                     info_data["address"] = address_lines[0] # Fallback to first line

            email_tag = soup.find("a", href=lambda href: href and href.startswith("mailto:info@kailashparbat.net"))
            if email_tag:
                info_data["email"] = email_tag.get_text(strip=True)

        # No specific phone number found in snippet for Head Office
        # info_data["phone"] remains "Not Available"

        # Create RestaurantInfo object to ensure schema compliance before returning dict
        try:
            restaurant_info_obj = RestaurantInfo(**info_data)
            logger.info(f"Scraped restaurant info: {restaurant_info_obj.dict()}")
            return restaurant_info_obj.dict()
        except Exception as e:
             logger.error(f"Pydantic validation error for RestaurantInfo: {e}")
             # Fallback to basic info if validation fails mid-way
             return RestaurantInfo(
                 name=info_data.get("name", "Kailash Parbat (Error)"),
                 address=info_data.get("address", "Not Available"),
                 phone=info_data.get("phone", "Not Available"),
                 website=url
             ).dict()

    def scrape_menu(self, url: str) -> List[Dict]:
        """Scrape menu items by finding and parsing a PDF link."""
        logger.info(f"Attempting to scrape menu from PDF on page: {url}")
        if not convert_from_bytes or not Image or not pytesseract:
             logger.error("Required libraries for PDF OCR (pdf2image, Pillow, pytesseract) or Tesseract executable itself are missing/not configured.")
             return []

        soup = self._make_request(url)
        if not soup:
            logger.warning(f"Failed to fetch page {url} to look for PDF menu.")
            return []

        pdf_link_tag = soup.find('a', href=lambda href: href and href.lower().endswith('.pdf'))
        menu_page_url = url # Start assuming the initial URL is the menu page

        # If PDF not found on initial URL, try navigating to a menu page
        if not pdf_link_tag:
            logger.warning(f"No PDF link found directly on {url}. Looking for a menu page link.")
            # Try finding a specific '/menu' link first, then a broader text search
            menu_link_tag = soup.find('a', href=re.compile(r'/menu/?$', re.IGNORECASE)) # Matches /menu or /menu/
            if not menu_link_tag:
                 menu_link_tag = soup.find('a', text=re.compile(r'menu', re.IGNORECASE), href=True)

            if menu_link_tag:
                menu_relative_url = menu_link_tag['href']
                menu_page_url = urljoin(url, menu_relative_url) # Use the initial URL as base
                logger.info(f"Found potential menu page link: {menu_page_url}. Fetching page.")
                menu_soup = self._make_request(menu_page_url)
                if menu_soup:
                    # Search again for the PDF link on the menu page
                    pdf_link_tag = menu_soup.find('a', href=lambda href: href and href.lower().endswith('.pdf'))
                    if not pdf_link_tag:
                         logger.warning(f"No PDF link found on the menu page either: {menu_page_url}")
                         return []
                    else:
                        logger.info(f"Found PDF link on the menu page: {menu_page_url}")
                else:
                    logger.warning(f"Failed to fetch the menu page: {menu_page_url}")
                    return [] # Stop if we couldn't fetch the menu page
            else:
                logger.warning(f"Could not find a link to a menu page on {url}. Cannot scrape menu from PDF.")
                return [] # Stop if we can't even find a menu link

        # If we found a pdf link (either on the initial page or the menu page)
        pdf_relative_url = pdf_link_tag['href']
        # Use the URL of the page where the PDF link was actually found as the base for urljoin
        pdf_full_url = urljoin(menu_page_url, pdf_relative_url)
        logger.info(f"Found PDF menu link: {pdf_full_url}")

        validated_menu_items = []
        try:
            # Download the PDF content
            response = requests.get(pdf_full_url, timeout=self.config.get("timeout", 15), headers={"User-Agent": self.config.get("user_agent")})
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            pdf_content = response.content # Get raw bytes

            logger.info("Converting PDF pages to images for OCR...")
            # Convert PDF bytes to a list of PIL Image objects
            images = convert_from_bytes(pdf_content)
            logger.info(f"Successfully converted PDF to {len(images)} image(s).")

            full_text = ""
            for i, image in enumerate(images):
                logger.debug(f"Performing OCR on page {i+1}/{len(images)}...")
                try:
                    # Use pytesseract to extract text from the image
                    # Add language if needed: lang='eng'
                    page_text = pytesseract.image_to_string(image)
                    if page_text:
                        full_text += page_text + "\n"
                        # Fix: Perform replace outside the f-string
                        log_text_preview = page_text[:100].replace('\n', ' ')
                        logger.debug(f"Extracted text chunk from page {i+1}: {log_text_preview}...")
                    else:
                        logger.warning(f"No text detected by OCR on page {i+1}.")
                except pytesseract.TesseractError as ocr_err:
                    logger.error(f"Tesseract OCR error on page {i+1}: {ocr_err}")
                except Exception as img_proc_err:
                    logger.error(f"Error processing image for page {i+1}: {img_proc_err}")

            # --- Basic Text Processing (Post-OCR) ---
            if not full_text:
                logger.warning(f"No text could be extracted via OCR from the PDF: {pdf_full_url}")
                return []

            lines = [line.strip() for line in full_text.splitlines() if line.strip()]
            logger.debug(f"Extracted lines from PDF: {lines[:20]}...") # Log first few lines

            # --- Filtering Logic ---
            potential_items = []
            ignore_keywords = [
                # Lowercase descriptive/common words
                "served with", "choose from", "garnished with", "cooked in", "topped with",
                "available", "special", "pcs", "bombay", "karachi", "india", "roadside halwai",
                "mulchandani brothers", "british india", "colaba market", "world map",
                "facebook.com", "twitter.com", "instagram", "#kailashparbatofficial", "100% veg",
                "chef's special", "jain available", "\u00a9", "contact", "franchise", "locations",
                "gallery", "about us", "home", "menu", "international", "asset", ".png", "coming soon",
                "taste the legend", "experience", "know more", "banquets", "outlets", "counting",
                "pure veg restaurant", "head office", "designed by", "website", "email", "phone",
                "address", "cuisine", "price", "category", "dietary info", "vegetarian", "vegan",
                "gluten free", "sweet / salted", "(2 pieces)", "or fried", "(2 pcs)",
                "dry / gravy", "dry/ gravy", "parsed from pdf", "from pdf",
                # Uppercase Headers/Non-items observed
                "a nte", "hailash o parbat", "chaats | dining", "more than 65 years",
                "of unbeatable", "history and tradition", "flavours of punjab", "| oriental",
                "our presence", "@ australia @ singapore", "® qatar", "since 1952",
                "kp famous since 1952",
                # Mixed/symbols to ignore
                "ez \\\\"
            ]
            # Regex to roughly match price/numeric lines
            price_pattern = re.compile(r'^\s*([\d.,]+\s*)+$|^\d+\)?$')
            # Regex to match lines that contain at least one lowercase letter
            lowercase_pattern = re.compile(r'[a-z]')

            for line in lines:
                # Skip processing if line is empty after potential stripping
                if not line:
                    continue

                line_lower = line.lower()

                # 1. Basic Length Filter
                if len(line) < 3 or len(line) > 70:
                    continue

                # 2. Ignore specific keywords/phrases (case-insensitive check)
                if any(keyword in line_lower for keyword in ignore_keywords):
                    continue

                # 3. Ignore lines that look like prices or just numbers/codes
                if price_pattern.match(line):
                    continue

                if lowercase_pattern.search(line):
                    continue

                # --- Line passed filters --- #
                potential_items.append(line)

            # --- Create Menu Items from Filtered Lines ---
            logger.info(f"Filtered down to {len(potential_items)} potential item names.")
            logger.debug(f"Potential items: {potential_items[:20]}...")

            for item_name in potential_items:
                item_data = {
                    "category": "From PDF", # Placeholder category
                    "name": item_name, # Use the filtered name
                    "description": "Parsed from PDF", # Placeholder description
                    "price": 0.0, # Price extraction needs specific logic
                    "dietary_info": {
                        "vegetarian": False, # Dietary info needs specific logic
                        "vegan": False,
                        "gluten_free": False
                    }
                }
                try:
                    menu_item_obj = MenuItem(**item_data)
                    validated_menu_items.append(menu_item_obj.dict())
                except Exception as e:
                    logger.error(f"Pydantic validation error for PDF MenuItem '{item_name}': {e}")

            logger.info(f"Created {len(validated_menu_items)} menu items after filtering.")

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download PDF from {pdf_full_url}: {e}")
            return []
        # Specific pdf2image/Pillow errors (less common for basic use)
        except Exception as pdf_img_err:
             # Catch potential errors during pdf2image conversion if any
             logger.error(f"Failed during PDF to image conversion for {pdf_full_url}: {pdf_img_err}")
             return []
        except Exception as e:
            logger.error(f"An unexpected error occurred during PDF OCR processing: {e}")
            logger.exception("Details of unexpected PDF OCR processing error:")
            return []

        if not validated_menu_items:
             logger.warning(f"Could not extract any menu items from the PDF at {pdf_full_url} using current heuristics.")

        return validated_menu_items

    def scrape_special_features(self, url: str) -> Dict:
        """Scrape special features conforming to SpecialFeatures schema."""
        logger.info(f"Scraping special features from {url}")
        soup = self._make_request(url)
        # Initialize with defaults from schema
        features_data = SpecialFeatures().dict()

        if not soup:
            return features_data # Return default features if request failed
        
        logger.info(f"Scraped special features: {features_data}")
        return features_data

    def scrape_operating_hours(self, url: str) -> Dict[str, Dict]:
        """Scrape operating hours conforming to Dict[str, OperatingHours] schema."""
        logger.info(f"Scraping operating hours from {url}")
        
        logger.warning("Operating hours not found on homepage. Returning empty dict.")
        return {}