from typing import Dict, List, Any
import re
from loguru import logger

class DataProcessor:
    """Processes and normalizes scraped restaurant data."""
    
    @staticmethod
    def clean_text(text: str) -> str:
        """Clean and normalize text."""
        if not text:
            return ""
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text.strip())
        # Remove special characters
        text = re.sub(r'[^\w\s-]', '', text)
        return text
    
    @staticmethod
    def normalize_price(price: str) -> Any:
        """Convert price string to float if possible, otherwise keep original."""
        if not price:
            return price
            
        try:
            # If it's already a number, return it as is
            if isinstance(price, (int, float)):
                return price
                
            # Try to extract a number if it's a string
            price_str = str(price)
            # Remove currency symbols and other non-numeric chars
            numeric_part = re.sub(r'[^\d.]', '', price_str)
            
            # If we have a valid number after extraction, convert to float
            if numeric_part:
                return float(numeric_part)
            else:
                # If no numeric part found, return original
                logger.info(f"No numeric part found in price: {price}, keeping original")
                return price
        except (ValueError, TypeError) as e:
            # If conversion fails, keep the original price string
            logger.warning(f"Could not normalize price: {price}, error: {str(e)}. Keeping original value.")
            return price
    
    @staticmethod
    def normalize_time(time_str: str) -> str:
        """Normalize time string to 24-hour format."""
        try:
            # Handle various time formats
            time_str = time_str.lower().strip()
            if not time_str:
                return ""
            
            # Convert 12-hour format to 24-hour
            if 'am' in time_str or 'pm' in time_str:
                from datetime import datetime
                time_obj = datetime.strptime(time_str, '%I:%M %p')
                return time_obj.strftime('%H:%M')
            
            return time_str
        except Exception as e:
            logger.warning(f"Could not normalize time: {time_str} - {str(e)}")
            return time_str
    
    @staticmethod
    def process_restaurant_info(info: Dict) -> Dict:
        """Process and normalize restaurant information."""
        return {
            "name": DataProcessor.clean_text(info.get("name", "")),
            "address": DataProcessor.clean_text(info.get("address", "")),
            "phone": DataProcessor.clean_text(info.get("phone", "")),
            "email": DataProcessor.clean_text(info.get("email", "")),
            "website": info.get("website", ""),
            "cuisine": [DataProcessor.clean_text(c) for c in info.get("cuisine", [])]
        }
    
    @staticmethod
    def process_menu_items(items: List[Dict]) -> List[Dict]:
        """Process and normalize menu items."""
        processed_items = []
        for item in items:
            # Extract dietary info properly, preserving the vegetarian flag
            dietary_info = item.get("dietary_info", {})
            
            # Add debugging to trace the dietary info values
            item_name = item.get("name", "Unknown")
            is_vegetarian = dietary_info.get("vegetarian", False)
            logger.debug(f"Processing item '{item_name}', raw vegetarian status: {is_vegetarian}")
            
            # Get original price for logging
            original_price = item.get("price", "")
            normalized_price = DataProcessor.normalize_price(original_price)
            
            # Log price normalization for debugging
            if original_price != normalized_price:
                logger.debug(f"Price for '{item_name}' normalized from '{original_price}' to '{normalized_price}'")
            
            processed_item = {
                "name": DataProcessor.clean_text(item.get("name", "")),
                "description": DataProcessor.clean_text(item.get("description", "")),
                "price": original_price,
                "category": DataProcessor.clean_text(item.get("category", "")),
                "dietary_info": {
                    # Use the extracted values from the dietary_info dict
                    "vegetarian": dietary_info.get("vegetarian", False),
                    "vegan": dietary_info.get("vegan", False),
                    "gluten_free": dietary_info.get("gluten_free", False)
                }
            }
            # Double-check the processed value
            logger.debug(f"Processed item '{processed_item['name']}', vegetarian status: {processed_item['dietary_info']['vegetarian']}, price: {processed_item['price']}")
            processed_items.append(processed_item)
        return processed_items
    
    @staticmethod
    def process_operating_hours(hours: Dict) -> Dict:
        """Process and normalize operating hours."""
        processed_hours = {}
        for day, schedule in hours.items():
            if isinstance(schedule, dict):
                processed_hours[day] = {
                    "open": DataProcessor.normalize_time(schedule.get("open", "")),
                    "close": DataProcessor.normalize_time(schedule.get("close", ""))
                }
        return processed_hours
    
    @staticmethod
    def process_special_features(features: Dict) -> Dict:
        """Process and normalize special features."""
        return {
            "delivery": features.get("delivery", False),
            "takeout": features.get("takeout", False),
            "reservations": features.get("reservations", False),
            "outdoor_seating": features.get("outdoor_seating", False),
            "wheelchair_accessible": features.get("wheelchair_accessible", False),
            "parking": features.get("parking", False),
            "wifi": features.get("wifi", False)
        }
    
    @staticmethod
    def process_all_data(data: Dict) -> Dict:
        """Process all scraped data."""
        try:
            return {
                "restaurant_info": DataProcessor.process_restaurant_info(
                    data.get("restaurant_info", {})
                ),
                "menu_items": DataProcessor.process_menu_items(
                    data.get("menu_items", [])
                ),
                "operating_hours": DataProcessor.process_operating_hours(
                    data.get("operating_hours", {})
                ),
                "special_features": DataProcessor.process_special_features(
                    data.get("special_features", {})
                )
            }
        except Exception as e:
            logger.error(f"Error processing data: {str(e)}")
            return {} 