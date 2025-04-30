from typing import Dict, List, Optional, Tuple, Set
import re
from bs4 import BeautifulSoup
from loguru import logger
from .base_scraper import BaseScraper
from knowledge_base.schema import Restaurant, RestaurantInfo, MenuItem, SpecialFeatures, OperatingHours
import json
import urllib.parse

class UniversalScraper(BaseScraper):
    """A universal scraper that can handle any restaurant website."""
    
    def __init__(self, config: Dict):
        """Initialize the scraper with configuration."""
        super().__init__(config)
        self.max_pages = config.get("max_pages", 5)
        self.content_cache = {}
    
    def _get_base_url(self, url: str) -> str:
        """Extract base URL from a full URL."""
        parsed = urllib.parse.urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    
    def _normalize_url(self, base_url: str, href: str) -> Optional[str]:
        """Normalize a URL by resolving relative URLs against the base URL."""
        if not href:
            return None
            
        # Handle relative URLs
        if href.startswith('/'):
            return urllib.parse.urljoin(base_url, href)
        # Handle absolute URLs
        elif href.startswith(('http://', 'https://')):
            return href
        # Handle relative URLs without leading slash
        else:
            return urllib.parse.urljoin(base_url + '/', href)
    
    def _is_same_domain(self, url1: str, url2: str) -> bool:
        """Check if two URLs are from the same domain."""
        domain1 = urllib.parse.urlparse(url1).netloc
        domain2 = urllib.parse.urlparse(url2).netloc
        return domain1 == domain2
    
    def _get_all_content(self, url: str) -> Dict[str, List[str]]:
        """Get all content from the website without filtering."""
        # Use cached content if available
        if url in self.content_cache:
            return self.content_cache[url]
            
        soup = self._make_request(url)
        if not soup:
            return {}
        
        # Get all text content with better separators for context
        all_text = soup.get_text(separator='\n', strip=True)
        
        # Get all links with full URLs
        all_links = set()
        base_url = self._get_base_url(url)
        for a in soup.find_all('a', href=True):
            href = a.get('href')
            normalized_url = self._normalize_url(base_url, href)
            if normalized_url:
                all_links.add(normalized_url)
        all_links = list(all_links)
        
        # Get all headings with hierarchy information
        headings = []
        for i in range(1, 7):
            for h in soup.find_all(f'h{i}'):
                text = h.get_text(strip=True)
                if text:
                    headings.append(text)
        
        # Get all paragraphs
        paragraphs = [p.get_text(strip=True) for p in soup.find_all('p') if p.get_text(strip=True)]
        
        # Get all list items
        list_items = [li.get_text(strip=True) for li in soup.find_all('li') if li.get_text(strip=True)]
        
        # Get all divs with text, filtering out very short ones
        divs = [div.get_text(strip=True) for div in soup.find_all('div') 
               if div.get_text(strip=True) and len(div.get_text(strip=True)) > 5]
        
        # Get all spans with text
        spans = [span.get_text(strip=True) for span in soup.find_all('span') 
                if span.get_text(strip=True) and len(span.get_text(strip=True)) > 3]
        
        # Get table data that might contain menu items or hours
        table_data = []
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                row_text = ' '.join([cell.get_text(strip=True) for cell in row.find_all(['td', 'th'])])
                if row_text:
                    table_data.append(row_text)
        
        # Extract meta tags that might contain useful info
        meta_data = []
        for meta in soup.find_all('meta'):
            if meta.get('name') and meta.get('content'):
                meta_data.append(f"{meta.get('name')}: {meta.get('content')}")
        
        # Look for elements with specific class names that might indicate important content
        class_elements = []
        important_classes = [
            'hours', 'address', 'location', 'contact', 'menu', 'food',
            'phone', 'email', 'social', 'feature', 'amenity', 'about'
        ]
        
        for cls in important_classes:
            for element in soup.find_all(class_=re.compile(cls, re.I)):
                text = element.get_text(strip=True)
                if text and len(text) > 3:
                    class_elements.append(text)
        
        # Extract alt text from images and check for parent links
        image_alt_texts = [] # For unlinked images or images with invalid/external links
        linked_image_info = [] # For images wrapped in valid, same-domain links
        base_url = self._get_base_url(url)
        for img in soup.find_all('img', alt=True):
            alt_text = img.get('alt', '').strip()
            if not alt_text or len(alt_text) <= 3: # Skip meaningless alt text
                continue

            parent_link = img.find_parent('a', href=True)
            link_url = None
            if parent_link:
                 href = parent_link.get('href')
                 normalized_url = self._normalize_url(base_url, href)
                 if normalized_url and self._is_same_domain(url, normalized_url):
                     # Check if it looks like a resource link (image, pdf, etc.)
                     parsed_link = urllib.parse.urlparse(normalized_url)
                     path = parsed_link.path.lower()
                     if not re.search(r'\\.(jpg|jpeg|png|gif|pdf|doc|docx|xls|xlsx|zip|mp4|mov|avi|css|js)$', path):
                         link_url = normalized_url # It's a potentially crawlable link

            if link_url:
                 linked_image_info.append({'alt': alt_text, 'link_url': link_url})
            else:
                 image_alt_texts.append(alt_text)
        
        # Extract social media links
        social_links = self._extract_social_media_links(all_links)
        
        # Extract structured data (JSON-LD) that might contain restaurant info
        structured_data = self._extract_structured_data(soup)
        
        # Store the result in cache
        result = {
            'all_text': all_text,
            'links': all_links,
            'headings': headings,
            'paragraphs': paragraphs,
            'list_items': list_items,
            'divs': divs,
            'spans': spans,
            'table_data': table_data,
            'meta_data': meta_data,
            'class_elements': class_elements,
            'structured_data': structured_data,
            'social_links': social_links,
            'image_alt_texts': image_alt_texts, # Alt texts from unlinked/invalid-link images
            'linked_image_info': linked_image_info # Info for images linked to potentially relevant pages
        }
        
        self.content_cache[url] = result
        return result
    
    def _extract_social_media_links(self, links: List[str]) -> Dict[str, str]:
        """Extract social media links from all URLs."""
        social_patterns = {
            'facebook': r'facebook\.com',
            'instagram': r'instagram\.com',
            'twitter': r'twitter\.com|x\.com',
            'linkedin': r'linkedin\.com',
            'youtube': r'youtube\.com',
            'tiktok': r'tiktok\.com',
            'yelp': r'yelp\.com',
            'tripadvisor': r'tripadvisor\.com',
            'zomato': r'zomato\.com',
            'doordash': r'doordash\.com',
            'ubereats': r'ubereats\.com',
            'grubhub': r'grubhub\.com'
        }
        
        social_links = {}
        for link in links:
            for platform, pattern in social_patterns.items():
                if re.search(pattern, link, re.I):
                    social_links[platform] = link
                    break
        
        return social_links
    
    def _extract_structured_data(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract and parse structured data (JSON-LD, microdata) from the page."""
        structured_data = []
        
        # Extract JSON-LD data
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                structured_data.append(data)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Error parsing JSON-LD: {e}")
        
        return structured_data
    
    def _find_relevant_pages(self, main_url: str, initial_content: Dict) -> Tuple[List[str], Set[str]]:
        """Find relevant pages from the main URL using already fetched initial content.
        Returns a tuple: (list_of_all_urls_to_scrape, set_of_menu_urls)."""
        # Use initial content passed to this function
        content = initial_content
        if not content: # Check if initial content fetch failed
            return [main_url], set() # Return main URL, empty set for menu URLs
            
        # Start with the main URL
        base_url = self._get_base_url(main_url)
        all_urls_set = {main_url} # Use a set for efficient adding and checking
        menu_urls_set = set()
        
        # Keywords for relevant pages
        page_keywords = {
            'menu': ['menu', 'food', 'dishes', 'cuisine', 'eat', 'order', 'catering', 'specialities', 'specials'],
            'contact': ['contact', 'find us', 'location', 'address', 'phone', 'email', 'directions'],
            'about': ['about', 'story', 'history', 'chef', 'team', 'our story'],
            'hours': ['hours', 'schedule', 'open', 'time', 'operation', 'timing'],
            'gallery': ['gallery', 'photos', 'images'],
            'reservations': ['reservation', 'booking', 'book']
        }
        
        # Check if the main URL itself is a menu page
        if any(keyword in main_url.lower() for keyword in page_keywords['menu']):
            menu_urls_set.add(main_url)
        
        # Find links that might contain relevant information
        relevant_urls = set()
        for link in content.get('links', []):
            # Skip non-http links
            if not link or not link.startswith('http'):
                continue
                
            # Skip external links
            if not self._is_same_domain(main_url, link):
                continue
                
            # Skip non-HTML resources more robustly
            parsed_link = urllib.parse.urlparse(link)
            path = parsed_link.path.lower()
            if re.search(r'\.(jpg|jpeg|png|gif|pdf|doc|docx|xls|xlsx|zip|mp4|mov|avi|css|js)$', path):
                continue
                
            # Check if the link path or query contains relevant keywords
            link_lower = link.lower()
            link_no_fragment = urllib.parse.urldefrag(link).url # Compare without fragment
            is_menu_link = False
            for category, keywords in page_keywords.items():
                if any(keyword in link_lower for keyword in keywords):
                    relevant_urls.add(link_no_fragment)
                    if category == 'menu':
                         is_menu_link = True
                    break # Found a category, stop checking keywords for this link
            
            if is_menu_link:
                 menu_urls_set.add(link_no_fragment)
        
        # Add relevant URLs to the list, up to the maximum
        count = 1 # Start with 1 for the main URL
        for url in relevant_urls:
            if url not in all_urls_set and count < self.max_pages:
                all_urls_set.add(url)
                # Add to menu_urls_set if it wasn't added directly via keywords but is relevant
                if url in menu_urls_set: # Check if already identified as menu link
                     pass # Already added
                elif any(keyword in url.lower() for keyword in page_keywords['menu']):
                     menu_urls_set.add(url)
                count += 1
        
        return list(all_urls_set), menu_urls_set
    
    def _extract_restaurant_info_from_structured_data(self, data: List[Dict]) -> Optional[Dict]:
        """Extract restaurant information from structured data."""
        for item in data:
            # Handle lists
            if isinstance(item, list):
                for subitem in item:
                    result = self._extract_restaurant_info_from_structured_data([subitem])
                    if result:
                        return result
            
            # Handle nested '@graph' array common in JSON-LD
            if isinstance(item, dict) and '@graph' in item:
                result = self._extract_restaurant_info_from_structured_data(item['@graph'])
                if result:
                    return result
                    
            # Check if this is a restaurant item
            if isinstance(item, dict) and ('@type' in item or 'type' in item):
                item_type = item.get('@type', item.get('type', ''))
                
                # Check for restaurant types
                if isinstance(item_type, str) and 'restaurant' in item_type.lower():
                    info = {}
                    
                    # Extract basic information
                    info['name'] = item.get('name', '')
                    
                    # Handle address
                    address = item.get('address', {})
                    if isinstance(address, dict):
                        address_parts = []
                        for part in ['streetAddress', 'addressLocality', 'addressRegion', 'postalCode']:
                            if part in address:
                                address_parts.append(str(address[part]))
                        if address_parts:
                            info['address'] = ', '.join(address_parts)
                    elif isinstance(address, str):
                        info['address'] = address
                    
                    # Get other information
                    info['phone'] = item.get('telephone', '')
                    info['email'] = item.get('email', '')
                    info['website'] = item.get('url', '')
                    
                    # Get cuisine
                    cuisine = item.get('servesCuisine', [])
                    if isinstance(cuisine, str):
                        info['cuisine'] = [cuisine]
                    elif isinstance(cuisine, list):
                        info['cuisine'] = cuisine
                    else:
                        info['cuisine'] = []
                    
                    return info
        
        return None
    
    def _extract_restaurant_info(self, content: Dict[str, List[str]]) -> Dict:
        """Extract restaurant information from all content."""
        # First try to extract from structured data
        if 'structured_data' in content and content['structured_data']:
            structured_info = self._extract_restaurant_info_from_structured_data(content['structured_data'])
            if structured_info and structured_info.get('name'):
                # If we found structured data, use it and supplement with any missing fields
                info = structured_info
                # Now continue with regular extraction for any missing fields
                if not info.get('address'):
                    info['address'] = self._extract_address(content)
                if not info.get('phone'):
                    info['phone'] = self._extract_phone(content)
                if not info.get('email'):
                    info['email'] = self._extract_email(content)
                if not info.get('website'):
                    info['website'] = self._extract_website(content)
                if not info.get('cuisine'):
                    info['cuisine'] = self._extract_cuisine(content)
                
                return RestaurantInfo(
                    name=info['name'] or "Unknown Restaurant",
                    address=info['address'] or "Address not available",
                    phone=info['phone'] or "Phone not available",
                    email=info['email'],
                    website=info['website'],
                    cuisine=info['cuisine']
                ).dict()
        
        # If no structured data, use the standard extraction
        info = {
            'name': '',
            'address': '',
            'phone': '',
            'email': '',
            'website': '',
            'cuisine': []
        }
        
        # Extract name - improved approach focusing on the actual restaurant name
        info['name'] = self._extract_restaurant_name(content)
        
        # Standard extraction methods
        info['address'] = self._extract_address(content)
        info['phone'] = self._extract_phone(content)
        info['email'] = self._extract_email(content)
        info['website'] = self._extract_website(content)
        info['cuisine'] = self._extract_cuisine(content)
        
        return RestaurantInfo(
            name=info['name'] or "Unknown Restaurant",
            address=info['address'] or "Address not available",
            phone=info['phone'] or "Phone not available",
            email=info['email'],
            website=info['website'],
            cuisine=info['cuisine']
        ).dict()
    
    def _extract_restaurant_name(self, content: Dict[str, List[str]]) -> str:
        """Extract the restaurant name using multiple approaches."""
        # 1. Check for Open Graph site name or Application Name
        for meta in content.get('meta_data', []):
            if meta.lower().startswith('og:site_name:'):
                name = meta.split(':', 1)[1].strip()
                if name and len(name) < 50: return name
            if meta.lower().startswith('application-name:'):
                name = meta.split(':', 1)[1].strip()
                if name and len(name) < 50: return name

        # 2. Check for site title in metadata (Improved filtering)
        for meta in content.get('meta_data', []):
            if meta.lower().startswith('title:') or meta.lower().startswith('og:title:'):
                title = meta.split(':', 1)[1].strip()
                # Remove common additions like "Home", "Menu", etc.
                title = re.sub(r'\s*[-|]\s*(Home|Menu|Contact|About|Location|Order Online|Reservations)$', '', title, flags=re.IGNORECASE).strip()
                # Prioritize shorter titles or parts before separators
                if ' | ' in title:
                    potential_name = title.split(' | ')[0].strip()
                    if len(potential_name) < 40: return potential_name
                if ' - ' in title:
                    potential_name = title.split(' - ')[0].strip()
                    if len(potential_name) < 40: return potential_name
                # If it's short and doesn't look like a price or generic term
                if len(title) < 30 and not title.startswith('Welcome') and not title.lower().startswith('home') and not re.match(r'^[$€£]', title):
                    return title
        
        # 3. Check for logo alt text or title attribute
        # (Assuming _get_all_content is modified to extract logo alt/title)
        # for logo_text in content.get('logo_texts', []):
        #     if logo_text and len(logo_text) < 50: return logo_text
                
        # 4. Look for the most prominent heading (H1 first)
        generic_terms = ['welcome', 'home', 'about', 'contact', 'menu', 'location', 'gallery', 'reservations', 'order']
        for heading_tag_num in range(1, 4): # Prioritize H1, H2, H3
            headings_in_tag = [h for h in content.get('headings', []) if h in content.get(f'h{heading_tag_num}_elements', [])] # Requires _get_all_content modification
            if not headings_in_tag: # Fallback if H tag info isn't available
                 headings_in_tag = content.get('headings', [])
            
            for heading in headings_in_tag:
                if 2 < len(heading) < 40:  # Reasonable length
                    # Ensure it's not just generic words or resembles a price
                    if not any(term in heading.lower() for term in generic_terms) and not re.match(r'^[$€£]', heading):
                        # Check if it contains common restaurant type words
                        if any(term in heading.lower() for term in ['restaurant', 'cafe', 'bistro', 'grill', 'kitchen', 'eatery', 'diner', 'pub']):
                            return heading
                        # Or if it appears frequently (might be the name repeated)
                        # Caution: This might pick up section titles if not careful
                        # if content['all_text'].lower().count(heading.lower()) > 2:
                        #    return heading

        # 5. Extract domain name from website as last resort (Improved formatting)
        if content.get('links'):
            # Try to find the canonical URL first
            # (Requires _get_all_content modification to find canonical links)
            # base_url_source = content.get('canonical_url', content.get('initial_url', '')) 
            base_url_source = content.get('links', [''])[0] # Simplified fallback

            if base_url_source and isinstance(base_url_source, str) and base_url_source.startswith('http'):
                domain_match = re.match(r'https?://(?:www\.)?([^/]+)', base_url_source)
                if domain_match:
                    domain_name = domain_match.group(1)
                    # Remove TLD and format nicely
                    restaurant_name = re.sub(r'\.(com|org|net|co|io|us|uk|ca|in)$', '', domain_name, flags=re.IGNORECASE)
                    restaurant_name = restaurant_name.replace('.', ' ').replace('-', ' ').strip()
                    # Capitalize words unless they are short prepositions/articles
                    restaurant_name = ' '.join(word if len(word) <= 3 and word.lower() in ['a', 'an', 'the', 'of', 'in', 'on', 'at', 'and'] else word.capitalize() for word in restaurant_name.split())
                    if restaurant_name: # Ensure we didn't just get a TLD
                        return restaurant_name
                        
        return "" # Return empty if no reliable name found
    
    def _extract_address(self, content: Dict[str, List[str]]) -> str:
        """Extract address from content with improved patterns and context."""
        # Use .get() for safe access
        search_elements = content.get('paragraphs', []) + content.get('divs', []) + content.get('class_elements', []) + content.get('list_items', []) + content.get('table_data', [])
        all_text_content = content.get('all_text', '')
        
        potential_addresses = []

        # Priority 1: Structured Data (if already processed)
        # This assumes _extract_restaurant_info handles structured data first
        # We don't need to re-parse it here, but this function might be called independently.

        # Priority 2: Look for explicit labels and context
        context_keywords = ['address', 'location', 'find us', 'visit us', 'directions', 'contact']
        for text in search_elements:
            text_lower = text.lower()
            # Check if text is likely within a contact/address section
            if any(keyword in text_lower for keyword in context_keywords):
                # Look for explicit labels like "Address:", "Location:", etc.
                match = re.search(r'(address|location|find us|visit us|directions)[:\\s]+(.*?)(?:\\n|\\r|$)', text, re.IGNORECASE | re.DOTALL)
                if match:
                    addr = match.group(2).strip()
                    # Basic validation: check length and presence of digits/letters
                    if 5 < len(addr) < 200 and re.search(r'\\d', addr) and re.search(r'[a-zA-Z]', addr):
                        potential_addresses.append(addr)

                # Also consider the text itself if it contains address-like patterns and context keywords
                elif re.search(r'\\d', text) and re.search(r'[a-zA-Z]', text) and 10 < len(text) < 200:
                     # Avoid adding just phone numbers or emails
                     if '@' not in text and not re.fullmatch(r'[\\d\\s().+-]+', text.strip()):
                        potential_addresses.append(text)

        # Priority 3: Search elements specifically marked with relevant classes
        for element in content.get('class_elements', []):
             if any(keyword in element.lower() for keyword in ['address', 'location']) and '@' not in element:
                 if re.search(r'\\d', element) and re.search(r'[a-zA-Z]', element) and 10 < len(element) < 200:
                     # Avoid adding just phone numbers
                     if not re.fullmatch(r'[\\d\\s().+-]+', element.strip()):
                          potential_addresses.append(element)
        
        # Stricter address patterns - focus on common formats
        # (Simplified and ordered by likely precision)
        address_patterns = [
            # US-like: 123 Main St, City, ST 12345 or 123 Main St, City, ST
            r'\\b\\d{1,6}\\s+(?:[A-Za-z0-9\\s.,#-]+(?:St|Street|Ave|Avenue|Rd|Road|Ln|Lane|Blvd|Boulevard|Dr|Drive|Ct|Court|Pl|Place|Way|Pkwy|Parkway))[,.]?\\s+[A-Za-z\\s\'-]+?,\\s*[A-Z]{2}\\s+(?:\\d{5}(?:-\\d{4})?)\\b',
            r'\\b\\d{1,6}\\s+(?:[A-Za-z0-9\\s.,#-]+(?:St|Street|Ave|Avenue|Rd|Road|Ln|Lane|Blvd|Boulevard|Dr|Drive|Ct|Court|Pl|Place|Way|Pkwy|Parkway))[,.]?\\s+[A-Za-z\\s\'-]+?,\\s*[A-Z]{2}\\b',
            # More general: Number Street, City/Town, Region/Postcode (allows international variations)
            r'\\b\\d{1,6}\\s+[A-Za-z0-9\\s.,#-]+?,\\s*[A-Za-z\\s\'-]+(?:,\\s*[A-Z0-9\\s-]{2,10})?\\b',
            # Simpler: Number Street Name, City/Town Name (less precise)
            r'\\b\\d{1,6}\\s+[A-Za-z0-9\\s.,#-]+\\b(?:\\s*,\\s*[A-Za-z\\s\'-]+)?',
            # PO Box
            r'P\\.?O\\.?\\s+Box\\s+\\d+'
        ]
        
        # Evaluate potential addresses found
        for addr_text in potential_addresses:
             # Clean up common prefixes/labels
             cleaned_addr = re.sub(r'^(address|location|find us|visit us|directions)[:\\s]+', '', addr_text, flags=re.IGNORECASE).strip()
             cleaned_addr = re.sub(r'\\s{2,}', ' ', cleaned_addr) # Consolidate whitespace
             
             # Check against stricter patterns
             for pattern in address_patterns:
                 match = re.search(pattern, cleaned_addr, re.IGNORECASE)
                 if match:
                     found_address = match.group(0).strip()
                     # Final check: ensure it doesn't look ONLY like a phone number
                     if not re.fullmatch(r'[\\d\\s().+-]+', found_address) and len(found_address) > 10:
                         # Prefer longer, more complete matches
                         # Example: prioritize "123 Main St, Anytown, CA 12345" over "123 Main St" if both match
                         return found_address # Return the first good match from prioritized sources
        
        # Last resort: Search all text content with patterns if nothing found yet
        logger.debug("No specific address sections found, searching all text content.")
        for pattern in address_patterns:
            # Search the whole text, but be cautious
            # Using finditer to potentially find the "best" match if needed
            matches = list(re.finditer(pattern, all_text_content, re.IGNORECASE))
            if matches:
                # Simple approach: return the first match found
                found_address = matches[0].group(0).strip()
                if not re.fullmatch(r'[\\d\\s().+-]+', found_address) and len(found_address) > 10:
                    # Avoid matching phone numbers embedded in address-like text
                    phone_in_address = re.search(r'\\b(?:\\+?1?\\s*\\(?\\d{3}\\)?[-.\\s]?\\d{3}[-.\\s]?\\d{4}|\\(?\\d{3}\\)?[-.\\s]?\\d{3}[-.\\s]?\\d{4})\\b', found_address)
                    if not phone_in_address or len(found_address) > 25: # Allow phone if address is long
                        return found_address

        logger.warning("Could not reliably extract address.")
        return "" # Return empty if no reliable address found
    
    def _extract_phone(self, content: Dict[str, List[str]]) -> str:
        """Extract phone number from content."""
        # Use .get() for safe access
        search_texts = content.get('paragraphs', []) + content.get('list_items', []) + content.get('divs', []) + content.get('class_elements', [])
        all_text_content = content.get('all_text', '')
        
        phone_patterns = [
            r'\+?1?\s*\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}',
            r'\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}',
            r'\+?[0-9]{1,3}[-.\s]?[0-9]{3,5}[-.\s]?[0-9]{3,5}'
        ]
        
        for text in search_texts:
            if any(keyword in text.lower() for keyword in ['phone', 'tel', 'call', 'contact']):
                for pattern in phone_patterns:
                    match = re.search(pattern, text)
                    if match:
                        return match.group(0)
                
        for pattern in phone_patterns:
            match = re.search(pattern, all_text_content)
            if match:
                return match.group(0)
                
        return ""
    
    def _extract_email(self, content: Dict[str, List[str]]) -> str:
        """Extract email from content with improved detection."""
        # Use .get() for safe access
        links = content.get('links', [])
        search_elements = content.get('paragraphs', []) + content.get('divs', []) + content.get('class_elements', []) + content.get('spans', [])
        all_text_content = content.get('all_text', '')
        
        for link in links:
            if link and link.startswith('mailto:'):
                email = link.replace('mailto:', '').split('?')[0].strip()
                if '@' in email:
                    return email
        
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        
        email_sections = []
        for text in search_elements:
            if any(term in text.lower() for term in ['email', 'mail', 'contact', 'write to us', 'email us', 'reach us']):
                email_sections.append(text)
        
        for text in email_sections:
            match = re.search(email_pattern, text)
            if match:
                return match.group(0)
        
        protected_patterns = [
            r'email:\s*([^@\s]+)\s*\[\s*at\s*\]\s*([^\s]+)',
            r'([^@\s]+)\s*\[\s*at\s*\]\s*([^\s]+)',
            r'([^@\s]+)\s*\(\s*at\s*\)\s*([^\s]+)',
            r'([^@\s]+)\s*AT\s*([^\s]+)'
        ]
        
        for text in email_sections:
            for pattern in protected_patterns:
                match = re.search(pattern, text, re.I)
                if match:
                    return f"{match.group(1)}@{match.group(2)}"
        
        for text in search_elements: # Search all elements again, not just specific sections
            match = re.search(email_pattern, text)
            if match:
                return match.group(0)
                
        match = re.search(email_pattern, all_text_content)
        if match:
            return match.group(0)
            
        return ""
    
    def _extract_website(self, content: Dict[str, List[str]]) -> str:
        """Extract website from content."""
        # Use .get() for safe access
        links = content.get('links', [])
        if links:
            for link in links:
                if link and isinstance(link, str) and link.startswith('http') and not link.startswith('https://cdn') and not link.startswith('https://www.google'):
                    base_url = re.match(r'https?://[^/]+', link)
                    if base_url:
                        # Prioritize non-social media domains if possible
                        domain = base_url.group(0)
                        if not any(social in domain for social in ['facebook', 'instagram', 'twitter', 'yelp']):
                            return domain
        # Fallback if only social media links found
        if links:
             for link in links:
                if link and isinstance(link, str) and link.startswith('http'):
                     base_url = re.match(r'https?://[^/]+', link)
                     if base_url:
                         return base_url.group(0)
        return ""
    
    def _extract_cuisine(self, content: Dict[str, List[str]]) -> List[str]:
        """Extract cuisine types from content."""
        # Use .get() for safe access
        search_texts = content.get('paragraphs', []) + content.get('list_items', []) + content.get('divs', [])
        all_text_content = content.get('all_text', '')
        cuisine_types = set()
        cuisine_keywords = [
            'indian', 'chinese', 'italian', 'mexican', 'american',
            'vegetarian', 'vegan', 'seafood', 'steakhouse', 'cafe',
            'thai', 'japanese', 'french', 'mediterranean', 'greek',
            'spanish', 'korean', 'vietnamese', 'brazilian', 'middle eastern',
             # Add more specific types
             'south indian', 'north indian', 'sushi', 'pizza', 'pasta', 'tacos',
             'burgers', 'bbq', 'ramen', 'pho', 'tapas', 'dim sum'
        ]
        context_keywords = ['cuisine', 'type of food', 'specialties', 'style', 'serves']
        
        for text in search_texts:
            if any(keyword in text.lower() for keyword in context_keywords):
                for cuisine in cuisine_keywords:
                    # Use word boundaries for more precise matching
                    if re.search(r'\b' + re.escape(cuisine) + r'\b', text, re.IGNORECASE):
                        cuisine_types.add(cuisine.capitalize())
        
        if not cuisine_types:
            for cuisine in cuisine_keywords:
                 if re.search(r'\b' + re.escape(cuisine) + r'\b', all_text_content, re.IGNORECASE):
                    cuisine_types.add(cuisine.capitalize())
        
        # Filter out generic terms that might have been added accidentally
        generic_terms_to_filter = {"Cuisine", "Type of food", "Specialties", "Style"}
        cuisine_types = {c for c in cuisine_types if c not in generic_terms_to_filter}
        
        return list(cuisine_types)
    
    def _make_request(self, url: str) -> Optional[BeautifulSoup]:
        """Make an HTTP request to the specified URL and return a BeautifulSoup object."""
        try:
            import requests
            from requests.exceptions import RequestException
            import time
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # Try to make the request with a timeout and retry logic
            max_retries = 3
            retry_delay = 2  # seconds
            
            for attempt in range(max_retries):
                try:
                    response = requests.get(url, headers=headers, timeout=10)
                    response.raise_for_status()  # Raise an exception for 4XX/5XX responses
                    
                    # Use the correct parser based on the content
                    if 'html' in response.headers.get('Content-Type', '').lower():
                        return BeautifulSoup(response.text, 'html.parser')
                    else:
                        logger.warning(f"Response from {url} is not HTML. Content-Type: {response.headers.get('Content-Type')}")
                        return None
                    
                except RequestException as e:
                    logger.warning(f"Request to {url} failed on attempt {attempt + 1}: {str(e)}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        logger.error(f"All attempts to request {url} failed. Last error: {str(e)}")
                        return None
            
        except ImportError:
            logger.error("Required module 'requests' is not installed")
            return None
        except Exception as e:
            logger.error(f"Unexpected error making request to {url}: {str(e)}")
            return None
        
        return None
    
    def _extract_menu_items(self, content: Dict[str, List[str]]) -> List[Dict]:
        """Extract menu items from all content with enhanced detection and filtering."""
        # Use .get() for safe access
        headings = content.get('headings', [])
        table_data = content.get('table_data', [])
        paragraphs = content.get('paragraphs', [])
        divs = content.get('divs', [])
        spans = content.get('spans', [])
        list_items = content.get('list_items', [])
        image_alt_texts = content.get('image_alt_texts', []) # Contains only menu page alts now
        all_text_content = content.get('all_text', '') # Needed for dietary check

        menu_items_raw = [] # Store potential items before validation
        
        # --- Identify Menu Sections ---
        menu_section_keywords = [
            'menu', 'dishes', 'food', 'specials', 'entrees', 'appetizers', 'desserts', 
            'lunch', 'dinner', 'breakfast', 'starters', 'mains', 'sides', 'beverages', 
            'thali', 'dosa', 'idly', 'vada', 'curry', 'biryani', 'chaat', 'tandoor', 
            'soups', 'salads', 'sandwiches', 'burgers', 'pizza', 'pasta', 'noodles', 'rice'
        ]
        # Add category names derived from common_categories in _determine_menu_category
        category_keywords = ['appetizer', 'starter', 'small plate', 'antipasti', 'entree', 'main', 'plate', 
                             'specialties', 'dessert', 'sweet', 'cake', 'ice cream', 'drink', 'beverage', 
                             'coffee', 'tea', 'wine', 'beer', 'breakfast', 'morning', 'brunch', 
                             'lunch', 'afternoon', 'dinner', 'evening']
        all_section_keywords = list(set(menu_section_keywords + category_keywords))
        
        menu_section_headings = []
        for heading in headings:
            heading_lower = heading.lower()
            if any(keyword in heading_lower for keyword in all_section_keywords):
                 # Avoid matching generic headings like 'Menu' if it's the main page title
                 if not (heading_lower == 'menu' and len(menu_section_headings) == 0): 
                    menu_section_headings.append(heading)
        logger.debug(f"Identified menu section headings: {menu_section_headings}")

        # --- Price Patterns ---
        price_patterns = [
            r'(?:[\\$€£]|Rs\\.?)\\s?(\\d+(?:[,.]\\d{1,2})?)', # $10.99, €10.99, £10.99, Rs 100, Rs.100
            r'(\\d+(?:[,.]\\d{1,2})?)\\s?(?:[\\$€£]|INR|USD|EUR|GBP)', # 10.99$, 100 INR
            r'(\\d+)\\s*(?:dollars|euros|pounds)' # 10 dollars
        ]
        combined_price_pattern = '|'.join(p.replace(r'\\d+(?:[,.]\\d{1,2})?', r'\\d+(?:[.,]\\d{1,2})?') for p in price_patterns) # More robust pattern for splitting

        # --- Process Text Elements for Potential Items ---
        
        # Combine relevant text sources
        potential_item_sources = table_data + paragraphs + divs + spans + list_items + image_alt_texts
        
        # Keywords indicating non-menu item text to filter out
        non_item_keywords = [
            'copyright', '©', 'rights reserved', 'privacy policy', 'terms', 'conditions',
            'address', 'location', 'phone', 'email', 'website', 'hours', 'contact', 
            'follow us', 'facebook', 'instagram', 'twitter', 'linkedin', 
            'directions', 'map', 'gallery', 'photos', 'reservations', 'booking', 
            'login', 'signup', 'account', 'password', 'username', 'search',
            'allergy information', 'nutritional info', 'calories', 'chef', 'story', 'about us',
            'delivery partner', 'powered by', 'designed by', 'catering request', 'event',
             # Specific examples from Saravana Bhavan JSON
             'saravana bhavan', 'interesting facts', 'travails of a trend setter', 'other services',
             'order now', 'add to cart', 'view cart', 'checkout',
             # Specific examples from Thalappakatti JSON
             'credit card', 'customer feedback', 'media coverage', 'branch', 'outlet',
             'restaurant', 'image', 'celebrities', 'career', 'investors', 'nutritional',
        ]
        
        processed_texts = set() # Avoid processing the exact same string multiple times

        for i, text in enumerate(potential_item_sources):
            logger.trace(f"Processing text element {i+1}/{len(potential_item_sources)}: '{text[:100]}...'") # Log start of processing
            if not text or text in processed_texts:
                logger.trace(f"  Skipping: Already processed or empty.")
                continue
            processed_texts.add(text)
            
            text_lower = text.lower()
            
            # --- Initial Filtering ---
            if len(text) < 3 or len(text) > 250: # Filter very short/long strings
                 logger.trace(f"  Skipping: Text length ({len(text)}) out of range (3-250).")
                 continue
            # **Explicitly skip identified section headings unless they have a price**
            cleaned_text_heading_check = re.sub(r'\s*\d+\s*images$', '', text, flags=re.IGNORECASE).strip()
            # **Strengthened Check**: Use the cleaned version for matching menu_section_headings as well
            if (text in menu_section_headings or cleaned_text_heading_check in menu_section_headings) and not re.search(combined_price_pattern, text, re.IGNORECASE):
                 logger.trace(f"  Skipping: Text matches identified menu section heading and has no price: '{text}'.")
                 continue
                 
            if text.isdigit() or re.fullmatch(r'[\\d\\s().+-]+', text): # Filter if only numbers/phone format
                 logger.trace(f"  Skipping: Text is numeric or phone-like.")
                 continue
            if '@' in text or text.startswith('http:') or text.startswith('https:'): # Filter emails/URLs
                 logger.trace(f"  Skipping: Text contains '@' or is a URL.")
                 continue
            if any(keyword in text_lower for keyword in non_item_keywords):
                 # Allow if it *also* contains a price (e.g., "Special Offer: Item $9.99")
                 if not re.search(combined_price_pattern, text, re.IGNORECASE):
                    logger.trace(f"  Skipping: Contains non-item keyword ('{[k for k in non_item_keywords if k in text_lower]}') and no price.")
                    continue
                 else:
                    logger.trace(f"  Contains non-item keyword BUT has price, proceeding.")
            # Filter text that looks like just a day/time range
            if re.match(r'(?:mon|tue|wed|thu|fri|sat|sun|daily).*?(?:-|to|–).*?(?:am|pm|\\d{1,2}:\\d{2})', text_lower):
                logger.trace(f"  Skipping: Text looks like an opening hours range.")
                continue

            logger.trace(f"  Passed initial filtering.")
            # --- Extract Name, Description, Price ---
            price_match = re.search(combined_price_pattern, text, re.IGNORECASE)
            
            if price_match:
                logger.trace(f"  Price pattern matched: '{price_match.group(0)}'")
                price_str_raw = price_match.group(0) # The full matched price string ($10.99, Rs.100, etc.)
                # Extract the numeric part - handle comma as decimal separator potentially
                price_val_str = None
                # Find the first non-null capturing group (should correspond to the numeric value)
                for group_num in range(1, len(price_match.groups()) + 1):
                     captured_group = price_match.group(group_num)
                     if captured_group:
                         price_val_str = captured_group
                         logger.trace(f"    Extracted price value string: '{price_val_str}'")
                         break
               
                if not price_val_str: 
                     logger.warning(f"  Price pattern matched but couldn't extract numeric value from: '{text}'")
                     continue 

                try:
                    # Normalize price string (remove currency symbols, spaces, use dot as decimal sep)
                    price_val_str_cleaned = re.sub(r'[^\\d.,]', '', price_val_str) 
                    price_val_str_cleaned = price_val_str_cleaned.replace(',', '.') # Use dot as decimal separator
                    price_value = float(price_val_str_cleaned)
                    logger.trace(f"    Converted price to float: {price_value}")
                except ValueError:
                    logger.warning(f"  Could not convert price '{price_val_str_cleaned}' (original: '{price_val_str}') to float in text: {text}")
                    continue

                # Price validation
                if not (0.1 <= price_value <= 1500): # Adjust price range if needed
                    logger.trace(f"    Skipping: Price {price_value} out of range (0.1-1500).")
                    continue

                # Try to split name and description based on price location
                price_index = text.find(price_str_raw)
                name = text[:price_index].strip()
                description = text[price_index + len(price_str_raw):].strip()
                logger.trace(f"    Initial split -> Name: '{name[:50]}...', Desc: '{description[:50]}...'")

                # Clean up potential artifacts around the split
                name = re.sub(r'[\\s.\\-:]+$', '', name).strip() # Remove trailing separators from name
                description = re.sub(r'^[\\s.\\-:]+', '', description).strip() # Remove leading separators from description

                # Basic name validation
                if not name or len(name) < 2 or name.isdigit():
                     logger.trace(f"    Skipping: Invalid name after price split ('{name}').")
                     # If name is empty/invalid, the price might be for the *previous* item in a list,
                     # or the format is unusual. Skip for now to avoid incorrect association.
                     # TODO: Could add logic to look back if context allows.
                     continue

                # Refine description (remove potential next item starts)
                # Look for patterns indicating a new item starts within the description part
                potential_next_item_match = re.search(r'\\n|\\r|\\t{2,}|\\s{4,}|[.,]\\s*(?:[\\$€£]|Rs)', description)
                if potential_next_item_match:
                    original_desc_len = len(description)
                    description = description[:potential_next_item_match.start()].strip()
                    logger.trace(f"    Refined description (removed potential next item start), length {original_desc_len} -> {len(description)}.")

                # Further name/description refinement (e.g., split long names)
                if len(name) > 80 and not description: 
                     # Try splitting by common separators like ' - ', ':', ' -- ', '...'
                     name_parts = re.split(r'\\s*[-–:]\\s+|\\s{2,}|\.{3,}', name, 1)
                     if len(name_parts) > 1 and len(name_parts[0]) > 2 and len(name_parts[0]) < 80:
                         original_name = name
                         name = name_parts[0].strip()
                         description = name_parts[1].strip()
                         logger.trace(f"    Split long name '{original_name[:50]}......' -> Name: '{name}', Desc: '{description[:50]}...'")
                
                # --- Clean final name ---
                original_name_before_clean = name
                name = re.sub(r'^[\\d.\\)\\s]+', '', name).strip() # Remove leading list markers
                name = re.sub(r'\s*\d+\s*images$', '', name, flags=re.IGNORECASE).strip() # Clean trailing "X images"
                name = re.sub(r'\s+ml$', '', name, flags=re.IGNORECASE).strip() # Clean trailing "ml"
                if not description:
                    name = re.sub(r'\\s*[\\.\\-\–:]+$', '', name).strip() # Clean trailing punctuation if no desc
                if name != original_name_before_clean:
                     logger.trace(f"    Cleaned name '{original_name_before_clean}' -> '{name}'")

                # Add to raw list if name seems valid
                if name and len(name) > 1:
                    logger.debug(f"  Adding item with price: Name='{name}', Price={price_value:.2f}, Desc='{description[:50]}...'")
                    menu_items_raw.append({
                        "name": name,
                        "description": description,
                        "price": price_value,
                        "source_text": text # Keep original text for category determination
                    })
                else:
                     logger.trace(f"  Skipping: Final name invalid after cleaning ('{name}').")
                   
            else:
                logger.trace(f"  No price pattern matched.")
                # --- Handle Potential Items WITHOUT Price ---
                # Be more conservative here. Only consider list items and (menu page) alt texts.
                if text in list_items or text in image_alt_texts:
                     logger.trace(f"    Checking as potential no-price item (list item or alt text).")
                     # Apply similar filtering as above, but be even stricter
                     if len(text) < 3 or len(text) > 100: 
                          logger.trace(f"      Skipping no-price: Length ({len(text)}) out of range (3-100).")
                          continue
                     if text.isdigit() or re.fullmatch(r'[\\d\\s().+-]+', text): 
                          logger.trace(f"      Skipping no-price: Numeric or phone-like.")
                          continue
                     if '@' in text or text.startswith('http:') or text.startswith('https:'): 
                          logger.trace(f"      Skipping no-price: Email or URL.")
                          continue
                     
                     # Enhanced filtering for non-menu items
                     # 1. Reject location names and common navigation elements
                     location_navigation_patterns = [
                         r'^(about|contact|press|news|latest|coverage|review|partner|award|road|nagar|layout|services|media)',
                         r'(road|nagar|layout|avenue|street|place|way|drive)$',
                         r'^(north|south|east|west)',
                         r'timings\s*:',
                         r'^\d+\s+\w+\s+\d+\s*$',    # Patterns like "5 Something 2022"
                         r'^\w+\s+\d+\s*$',          # Patterns like "Something 2022"
                         r'copy$',                   # Image filenames often end with "copy"
                         r'\d+x\d+',                 # Image dimensions like "1024x683"
                         r'^with\s+',                # "with someone" photo captions
                         r'^group\s+\d+',            # Group photo captions
                         r'^frame\s+\d+'             # Frame photo captions
                     ]
                     
                     if any(re.search(pattern, text_lower, re.IGNORECASE) for pattern in location_navigation_patterns):
                         logger.trace(f"      Skipping no-price: Matches location/navigation/image pattern: '{text}'")
                         continue
                     
                     # 2. Check for food-related keywords to identify true menu items
                     food_related_terms = [
                         'soup', 'salad', 'platter', 'curry', 'fried', 'rice', 'noodles', 'bread', 'dosa', 
                         'idli', 'vada', 'sambar', 'chutney', 'masala', 'paneer', 'butter', 'gravy', 'dal',
                         'biryani', 'pulao', 'thali', 'paratha', 'roti', 'naan', 'chaat', 'puri', 'bhaji',
                         'dessert', 'sweet', 'coffee', 'tea', 'juice', 'drink', 'lassi', 'shake', 'special'
                     ]
                     
                     has_food_term = any(term in text_lower for term in food_related_terms)
                     
                     # **Check again for section heading match (redundant but safe)**
                     cleaned_text_heading_check = re.sub(r'\s*\d+\s*images$', '', text, flags=re.IGNORECASE).strip()
                     if text in menu_section_headings or cleaned_text_heading_check in menu_section_headings:
                         logger.trace(f"      Skipping no-price: Text matches identified menu section heading: '{text}'.")
                         continue
                         
                     # Stricter keyword filtering for no-price items
                     strict_non_item_keywords = non_item_keywords + menu_section_keywords + category_keywords
                     if any(keyword in text_lower for keyword in strict_non_item_keywords):
                         logger.trace(f"      Skipping no-price: Contains strict non-item keyword ('{[k for k in strict_non_item_keywords if k in text_lower]}').")
                         continue
                         
                     # Check if it looks plausibly like a food item 
                     # For no-price items, require either:
                     # 1. Contains a food-related term, OR
                     # 2. Matches known food item patterns
                     
                     food_item_patterns = [
                         # Common Indian dish naming patterns
                         r'\b(aloo|paneer|gobi|palak|chana|dal|matar|bhindi|baingan|mushroom|malai|tikka|tandoori|kadai|korma|masala|butter)\b',
                         # Common dish suffixes
                         r'(curry|fried|roasted|grilled|baked|sauteed|special)\b',
                         # Common dish structures (e.g., X with Y)
                         r'\s+with\s+',
                         # Likely food descriptions
                         r'served\s+with',
                         r'topped\s+with',
                         r'garnished\s+with'
                     ]
                     
                     matches_food_pattern = any(re.search(pattern, text_lower, re.IGNORECASE) for pattern in food_item_patterns)
                     
                     # Criteria for accepting no-price item: Must be reasonable length, have multiple words,
                     # and either contain a food term or match a food pattern
                     if (1 < len(text.split()) < 10) and (has_food_term or matches_food_pattern):
                         # **Check if name ends with 'X images' pattern**
                         if re.search(r'\d+\s*images$', text, flags=re.IGNORECASE):
                              logger.trace(f"      Skipping no-price: Text ends with 'X images' pattern.")
                              continue
                              
                         logger.trace(f"      Looks like a plausible no-price food item.")
                         name = text.strip()
                         # Clean name
                         original_name_before_clean = name
                         name = re.sub(r'^[\\d.\\)\\s]+', '', name).strip()
                         name = re.sub(r'\s*\d+\s*images$', '', name, flags=re.IGNORECASE).strip() # Clean trailing "X images"
                         name = re.sub(r'\s+ml$', '', name, flags=re.IGNORECASE).strip() # Clean trailing "ml"
                         name = re.sub(r'\\s*[\\.\\-\–:]+$', '', name).strip() # Clean trailing punctuation
                         if name != original_name_before_clean:
                             logger.trace(f"        Cleaned no-price name '{original_name_before_clean}' -> '{name}'")

                         if name and len(name) > 1:
                            logger.debug(f"  Adding item WITHOUT price: Name='{name}'")
                            menu_items_raw.append({
                                "name": name,
                                "description": "",
                                "price": 0.0, # Price unknown
                                "source_text": text
                            })
                         else:
                             logger.trace(f"      Skipping no-price: Final name invalid after cleaning ('{name}').")
                     else:
                          logger.trace(f"      Skipping no-price: Failed food item plausibility checks")
                else:
                     logger.trace(f"    Skipping: Not a list item or alt text, and no price found.")

        # --- Final Processing and Deduplication ---
        final_menu_items = []
        seen_signatures = set()

        # Determine category and dietary info for each valid raw item
        for item_data in menu_items_raw:
            name = item_data['name']
            price = item_data['price']
            source_text = item_data['source_text']
            
            # Normalize name for signature generation
            norm_name = re.sub(r'[^a-zA-Z0-9]', '', name.lower())
            if not norm_name: continue # Skip if name normalization results in empty string

            # Create signature for deduplication
            # Use price in signature only if > 0
            signature = f"{norm_name}_{price:.2f}" if price > 0 else norm_name
            
            if signature not in seen_signatures:
                seen_signatures.add(signature)
                
                # Determine category based on nearest heading or keywords in text
                category = self._determine_menu_category(source_text, menu_section_headings)
                # Extract dietary info
                dietary_info = self._extract_dietary_info(source_text) # Or pass item_data if needed
                
                final_menu_items.append(MenuItem(
                    name=name,
                    description=item_data['description'],
                    price=price,
                    category=category,
                    dietary_info=dietary_info
                ).dict())

        logger.info(f"Extracted {len(final_menu_items)} unique menu items after filtering.")
        return final_menu_items
    
    def _determine_menu_category(self, item_text: str, menu_sections: List[str]) -> str:
        """Determine the menu category for an item, prioritizing nearby sections."""
        # TODO: This could be improved by knowing the actual HTML structure or text position
        # For now, use keywords in the item text itself or the identified section headings.
        
        common_categories = {
            # Order matters slightly - check more specific first if overlapping keywords
            'breakfast': ['breakfast', 'morning', 'brunch'],
            'lunch': ['lunch', 'afternoon'],
            'dinner': ['dinner', 'evening'],
            'appetizer': ['appetizer', 'starter', 'small plate', 'antipasti', 'chaat', 'tapas'],
            'soup': ['soup', 'rasam'],
            'salad': ['salad'],
            'entree': ['entree', 'main', 'plate', 'specialties', 'thali', 'curry', 'biryani', 'tandoor', 'grill'],
            'side': ['side', 'accompaniment', 'extra', 'bread', 'naan', 'roti', 'rice'],
            'dessert': ['dessert', 'sweet', 'cake', 'ice cream', 'pastry', 'falooda'],
            'beverage': ['drink', 'beverage', 'coffee', 'tea', 'juice', 'smoothie', 'lassi', 'soda', 'water', 'wine', 'beer', 'cocktail']
        }
        
        item_text_lower = item_text.lower()

        # Check item text directly for category keywords first
        for category, keywords in common_categories.items():
            for keyword in keywords:
                 # Use word boundaries for better matching
                if re.search(r'\b' + re.escape(keyword) + r'\b', item_text_lower):
                    return category.capitalize()
        
        # If not found in item text, check against the list of identified menu section headings
        # This assumes menu_sections contains headings like "Appetizers", "Main Courses" etc.
        # A simple approach: check if any section heading contains category keywords.
        # (A better approach would find the *closest preceding* heading, but that requires position info)
        for section_heading in menu_sections: # Iterate through identified headings
            section_lower = section_heading.lower()
            for category, keywords in common_categories.items():
                if any(re.search(r'\b' + re.escape(keyword) + r'\b', section_lower) for keyword in keywords):
                    # Found a potential category match in a section heading.
                    # We don't know if this item *belongs* to this section without structure/position.
                    # As a heuristic, let's return this category if found.
                    # This might misclassify items if sections aren't clearly separated in the raw text.
                    return category.capitalize()
        
        return "Uncategorized" # Default if no category found
    
    def _extract_dietary_info(self, text: str) -> Dict:
        """Extract dietary information from the text."""
        text_lower = text.lower()
        
        # Improved markers for dietary info
        vegetarian_markers = [
            'vegetarian', ' veg ', 'veg.', '(v)', 'veggie', 'no meat', 
            'plant-based', 'meatless', 'vegetable', 'veg option'
        ]
        
        vegan_markers = [
            'vegan', '(vg)', '(ve)', 'plant-based', 'dairy-free', 'no dairy', 
            'no animal', 'no egg', 'no honey'
        ]
        
        gluten_free_markers = [
            'gluten-free', 'gluten free', 'gf', '(gf)', 'no gluten', 
            'without gluten', 'gluten friendly'
        ]
        
        # For Indian dishes, many are inherently vegetarian
        # Check for known vegetarian Indian dishes (if no other info is given)
        vegetarian_indian_dishes = [
            'paneer', 'palak', 'aloo', 'gobi', 'dal', 'chana', 'rajma', 'bhindi', 
            'baingan', 'saag', 'malai kofta', 'navratan', 'veg', 'dosa', 'idli', 
            'sambar', 'rasam', 'uttapam', 'upma', 'puri', 'chaat', 'pakora', 
            'bhaji', 'sabzi', 'khichdi', 'chole'
        ]
        
        # Non-vegetarian markers for Indian food
        non_vegetarian_markers = [
            'chicken', 'mutton', 'lamb', 'beef', 'fish', 'prawn', 'shrimp', 
            'seafood', 'meat', 'egg', 'non-veg', 'nonveg', 'non veg'
        ]
        
        # Get the name from the text if available (will help with dish-specific inference)
        dish_name = text.split('\n')[0] if '\n' in text else text
        dish_name_lower = dish_name.lower()
        
        # Check direct markers first
        is_vegetarian = any(marker in text_lower for marker in vegetarian_markers)
        is_vegan = any(marker in text_lower for marker in vegan_markers)
        is_gluten_free = any(marker in text_lower for marker in gluten_free_markers)
        
        # If no direct vegetarian marker found, infer from dish name for Indian restaurants
        if not is_vegetarian and not any(marker in text_lower for marker in non_vegetarian_markers):
            # Check if it contains any known vegetarian Indian dish names
            is_vegetarian = any(veg_dish in dish_name_lower for veg_dish in vegetarian_indian_dishes)
            
            # If it's a restaurant whose name suggests it's vegetarian (like many South Indian places)
            if 'paakashala' in text_lower or 'udupi' in text_lower or 'saravanaa' in text_lower:
                is_vegetarian = True
        
        return {
            "vegetarian": is_vegetarian,
            "vegan": is_vegan,
            "gluten_free": is_gluten_free
        }
    
    def _extract_special_features(self, content: Dict[str, List[str]]) -> Dict:
        """Extract special features from all content."""
        features = SpecialFeatures()
        
        # Check for features in all text content
        all_text = ' '.join(content['all_text'].split())
        
        # More comprehensive feature patterns with contextual clues
        feature_patterns = {
            "delivery": [
                r"delivery", r"delivers", r"delivery available", r"order online", 
                r"brought to you", r"home delivery", r"get it delivered", r"doordash", 
                r"ubereats", r"grubhub", r"seamless", r"food delivery", r"deliver to your door"
            ],
            "takeout": [
                r"takeout", r"take[- ]?away", r"to[- ]?go", r"pickup", r"carry[- ]?out", 
                r"order ahead", r"grab and go", r"pick up at", r"curbside", r"call ahead"
            ],
            "reservations": [
                r"reservation", r"booking", r"book a table", r"reserve", r"make a reservation",
                r"book online", r"book now", r"reserve a table", r"table booking", r"opentable"
            ],
            "outdoor_seating": [
                r"outdoor[- ]?seating", r"patio", r"terrace", r"al fresco", r"deck", 
                r"garden seating", r"rooftop", r"outdoor dining", r"sidewalk seating", 
                r"outside tables"
            ],
            "wheelchair_accessible": [
                r"wheelchair[- ]?accessible", r"disabled[- ]?access", r"accessibility", 
                r"ada compliant", r"handicap", r"accessible entrance", r"disability", r"accessible restroom"
            ],
            "parking": [
                r"parking", r"car[- ]?park", r"free parking", r"valet", r"lot", r"garage",
                r"parking available", r"self[- ]?parking", r"street parking", r"parking lot"
            ],
            "wifi": [
                r"wifi", r"wireless", r"free wifi", r"internet", r"wi-fi", r"hotspot", 
                r"connected", r"high-speed internet", r"complimentary wifi"
            ]
        }
        
        # Add more features that are commonly found in restaurants
        additional_features = {
            "happy_hour": [
                r"happy hour", r"discounted drinks", r"drink specials", r"half price", 
                r"discount between", r"special price", r"happy hr"
            ],
            "live_music": [
                r"live music", r"band", r"performance", r"live entertainment", r"music venue",
                r"live jazz", r"live performances", r"artists perform", r"concerts", r"shows"
            ],
            "kids_friendly": [
                r"kids menu", r"children", r"family friendly", r"kids eat free", r"child", 
                r"kid friendly", r"family restaurant", r"playground", r"kids corner"
            ],
            "alcohol_served": [
                r"full bar", r"cocktails", r"beer", r"wine", r"spirits", r"happy hour",
                r"alcoholic beverages", r"bar menu", r"drinks menu", r"alcoholic"
            ]
        }
        
        # Combine all feature patterns
        all_feature_patterns = {**feature_patterns, **additional_features}
        
        # Check for features in context
        feature_contexts = []
        for text in content['paragraphs'] + content['list_items'] + content['divs']:
            if any(keyword in text.lower() for keyword in [
                'feature', 'amenities', 'services', 'offer', 'available', 'facilities',
                'what we offer', 'restaurant features', 'about us'
            ]):
                feature_contexts.append(text)
        
        # First look in feature contexts
        for text in feature_contexts:
            for feature, patterns in all_feature_patterns.items():
                for pattern in patterns:
                    if re.search(r'\b' + pattern + r'\b', text, re.I):
                        if hasattr(features, feature):
                            setattr(features, feature, True)
                        else:
                            # For additional features not in the base model
                            features.__dict__[feature] = True
                        break
        
        # Then check all text content
        for feature, patterns in all_feature_patterns.items():
            # Skip if already found
            if hasattr(features, feature) and getattr(features, feature):
                continue
                
            for pattern in patterns:
                if re.search(r'\b' + pattern + r'\b', all_text, re.I):
                    if hasattr(features, feature):
                        setattr(features, feature, True)
                    else:
                        # For additional features not in the base model
                        features.__dict__[feature] = True
                    break
        
        # Check for negative statements that might indicate a feature is not available
        negative_patterns = [
            r"not available", r"no \w+ available", r"don't offer", r"do not offer",
            r"not provided", r"unavailable", r"no longer", r"temporarily unavailable"
        ]
        
        for feature in all_feature_patterns.keys():
            if hasattr(features, feature) and getattr(features, feature):
                for pattern in all_feature_patterns[feature]:
                    for neg_pattern in negative_patterns:
                        neg_search = re.search(
                            r'\b' + neg_pattern + r'.*?\b' + pattern + r'\b|' +
                            r'\b' + pattern + r'.*?\b' + neg_pattern + r'\b',
                            all_text, re.I
                        )
                        if neg_search:
                            if hasattr(features, feature):
                                setattr(features, feature, False)
                            else:
                                features.__dict__[feature] = False
                            break
        
        # Convert to dict but only include the fields from the original model
        result = features.dict()
        
        # Add any additional detected features
        for feature in additional_features.keys():
            if hasattr(features, feature):
                result[feature] = getattr(features, feature)
        
        return result
    
    def _extract_operating_hours(self, content: Dict[str, List[str]]) -> Dict:
        """Extract operating hours from all content."""
        hours = {}
        
        # Common time patterns - more comprehensive
        time_patterns = [
            r'\d{1,2}(?::\d{2}|\.\d{2})?\s*(?:AM|PM|am|pm)',  # 12:30 PM, 12 PM, or 12.30 PM
            r'\d{1,2}(?::\d{2}|\.\d{2})?\s*(?:a|p)\.?m\.?',   # 12:30 a.m., 12 p.m., or 12.30 a.m.
            r'\d{1,2}(?::\d{2}|\.\d{2})?\s*(?:A|P)\.?M\.?',   # 12:30 A.M., 12 P.M., or 12.30 A.M.
            r'\d{1,2}h\d{2}',                         # 12h30 (European format)
            r'\d{2}:\d{2}(?:\s*hrs)?'                 # 14:30 or 14:30 hrs (24h format)
        ]
        
        # First, look specifically for "Timings:" pattern which is common in Indian restaurants
        timings_pattern = re.compile(r'timings\s*:\s*(\d{1,2}(?::\d{2}|\.\d{2})?\s*(?:AM|PM|am|pm))\s*-\s*(\d{1,2}(?::\d{2}|\.\d{2})?\s*(?:AM|PM|am|pm))', re.IGNORECASE)
        
        all_text = content.get('all_text', '')
        all_elements = content.get('paragraphs', []) + content.get('divs', []) + content.get('list_items', []) + content.get('spans', [])
        
        # Check for timings pattern first
        timings_found = False
        for element in all_elements:
            match = timings_pattern.search(element)
            if match:
                open_time = match.group(1)
                close_time = match.group(2)
                # Apply these hours to all days
                for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
                    hours[day] = OperatingHours(
                        open=open_time,
                        close=close_time
                    ).dict()
                timings_found = True
                break
        
        if timings_found:
            return hours
            
        # If no timings pattern found, proceed with the more general approach
        # Look for hours contexts in paragraphs and list items
        hours_paragraphs = []
        for text in content['paragraphs'] + content['list_items'] + content['divs']:
            if any(word in text.lower() for word in ['hours', 'opening', 'schedule', 'timing', 'open', 'closed']):
                hours_paragraphs.append(text)
        
        # Days of the week + common variations
        day_patterns = {
            "monday": [r'mon(?:day)?', r'm\s*-\s*', r'monday[s]?'],
            "tuesday": [r'tue(?:s(?:day)?)?', r't\s*-\s*', r'tuesday[s]?'],
            "wednesday": [r'wed(?:nesday)?', r'w\s*-\s*', r'wednesday[s]?'],
            "thursday": [r'thu(?:rs(?:day)?)?', r'th\s*-\s*', r'thursday[s]?'],
            "friday": [r'fri(?:day)?', r'f\s*-\s*', r'friday[s]?'],
            "saturday": [r'sat(?:urday)?', r's\s*-\s*', r'saturday[s]?'],
            "sunday": [r'sun(?:day)?', r'su\s*-\s*', r'sunday[s]?']
        }
        
        # Check if we have a consistent hours format across multiple days
        for text in hours_paragraphs:
            # Check for ranges like "Monday-Friday: 9am-5pm"
            for time_pattern in time_patterns:
                range_match = re.search(
                    r'((?:mon|tue|wed|thu|fri|sat|sun)[^-]*?-[^:]*?(?:mon|tue|wed|thu|fri|sat|sun)[^:]*):\s*(' 
                    + time_pattern + r')\s*(?:-|–|to|til|until)\s*(' + time_pattern + r')',
                    text.lower()
                )
                
                if range_match:
                    day_range = range_match.group(1).lower()
                    open_time = range_match.group(2)
                    close_time = range_match.group(3)
                    
                    # Determine which days are in the range
                    start_day = None
                    end_day = None
                    
                    for day, patterns in day_patterns.items():
                        for pattern in patterns:
                            if re.search(pattern, day_range.split('-')[0].strip()):
                                start_day = day
                            if re.search(pattern, day_range.split('-')[1].strip()):
                                end_day = day
                    
                    if start_day and end_day:
                        # Get the indices of the days
                        days_ordered = list(day_patterns.keys())
                        start_idx = days_ordered.index(start_day)
                        end_idx = days_ordered.index(end_day)
                        
                        # Handle wrapping around the week
                        if end_idx < start_idx:
                            end_idx += 7
                        
                        # Fill in all days in the range
                        for idx in range(start_idx, end_idx + 1):
                            actual_idx = idx % 7
                            day = days_ordered[actual_idx]
                            hours[day] = OperatingHours(
                                open=open_time,
                                close=close_time
                            ).dict()
        
        # If no range formats found, look for individual day patterns
        if not hours:
            for day, day_pattern_list in day_patterns.items():
                for day_pattern in day_pattern_list:
                    for text in hours_paragraphs:
                        # Match day followed by hours
                        for time_pattern in time_patterns:
                            pattern = f"({day_pattern}).*?({time_pattern}).*?(?:-|–|to|til|until).*?({time_pattern})"
                            match = re.search(pattern, text.lower())
                            
                            if match:
                                hours[day] = OperatingHours(
                                    open=match.group(2),
                                    close=match.group(3)
                                ).dict()
                                break
                        
                        # Also check for "closed" days
                        if re.search(f"{day_pattern}.*?closed", text.lower()):
                            hours[day] = OperatingHours(
                                open="Closed",
                                close="Closed"
                            ).dict()
                            
                        if day in hours:
                            break
        
        # As a last resort, look in all content for hours
        if not hours:
            all_text = ' '.join(content['all_text'].split())
            
            # Look for a generic opening hours section
            for time_pattern in time_patterns:
                hours_match = re.search(
                    r'open(?:ing)?(?:\s+hours)?:?\s*(' + time_pattern + r')\s*(?:-|–|to|til|until)\s*(' + time_pattern + r')',
                    all_text.lower()
                )
                
                if hours_match:
                    # Apply these hours to all days
                    for day in day_patterns.keys():
                        hours[day] = OperatingHours(
                            open=hours_match.group(1),
                            close=hours_match.group(2)
                        ).dict()
                    break
        
        return hours
    
    def scrape_all(self, url: str) -> Dict:
        """Scrape all restaurant information from multiple pages, prioritizing menu pages."""
        try:
            self.content_cache = {}
            processed_urls = set()
            all_content_aggregated_non_menu = {} # For address, hours, features etc.
            menu_content_aggregated = {'image_alt_texts': []} # Specifically for menu items + alt texts
            aggregated_menu_alt_texts = set()
            
            # Initial setup & find primary pages
            initial_content = self._get_all_content(url)
            if not initial_content:
                logger.error(f"Could not fetch initial URL: {url}. Aborting scrape.")
                return {}
                
            primary_urls_to_scrape, menu_page_urls = self._find_relevant_pages(url, initial_content)
            logger.info(f"Found {len(primary_urls_to_scrape)} primary pages. Identified {len(menu_page_urls)} as menu pages: {menu_page_urls}")
            
            urls_to_scrape_queue = list(primary_urls_to_scrape) # Use list as queue
            image_linked_urls_found = set() # Track URLs found via image links from menu pages

            # Function to safely merge list-based content (generic, excluding image lists)
            def merge_content(target_dict, source_dict): 
                skipped_keys = {'image_alt_texts', 'linked_image_info'}
                for key, value in source_dict.items():
                    if key in skipped_keys:
                        continue
                    if not value:
                        continue
                    if key not in target_dict or not target_dict[key]:
                        target_dict[key] = value
                    elif isinstance(value, list) and isinstance(target_dict.get(key), list):
                        dedup_keys_set = {'links', 'headings', 'class_elements', 'meta_data'}
                        append_keys = {'paragraphs', 'list_items', 'divs', 'spans', 'table_data', 'structured_data'}
                        if key in dedup_keys_set:
                            try:
                                combined = target_dict.get(key, []) + value # Ensure target_dict[key] exists
                                hashable_items = [item for item in combined if isinstance(item, (str, int, float, tuple))]
                                target_dict[key] = list(set(hashable_items))
                            except TypeError as te:
                                logger.warning(f"Could not deduplicate key '{key}' using set ({te}), appending instead.")
                                existing_list = target_dict.get(key, [])
                                for item in value:
                                    if item not in existing_list:
                                        existing_list.append(item)
                                target_dict[key] = existing_list
                        elif key in append_keys:
                             if key not in target_dict: target_dict[key] = [] # Initialize if not present
                             target_dict[key].extend(value)
                    elif isinstance(value, str) and isinstance(target_dict.get(key, ''), str):
                        if key == 'all_text' and value not in target_dict.get(key, ''):
                             if key not in target_dict: target_dict[key] = "" # Initialize if not present
                             target_dict[key] += "\n" + value
                    elif isinstance(value, dict) and isinstance(target_dict.get(key), dict):
                        target_dict[key].update(value)
            
            # --- Main scraping loop --- 
            crawl_limit = self.max_pages * 2 
            queue_to_process = list(urls_to_scrape_queue) # Start with a copy of primary URLs
            processed_count = 0

            while queue_to_process and processed_count < crawl_limit:
                current_url = queue_to_process.pop(0) # FIFO processing
                
                if current_url in processed_urls:
                    continue

                is_primary_url = current_url in urls_to_scrape_queue # Was it in the initial list?
                is_image_linked_url = current_url in image_linked_urls_found # Was it found via an image link?
                log_prefix = "[ImgLink]" if is_image_linked_url else ("[Primary]" if is_primary_url else "[Unknown]")
                
                logger.debug(f"{log_prefix} Processing URL ({processed_count + 1}/{crawl_limit}): {current_url}")
                processed_urls.add(current_url)
                processed_count += 1
                
                content = self._get_all_content(current_url)
                if not content:
                    logger.warning(f"{log_prefix} Failed to get content for {current_url}, skipping.")
                    continue

                is_primary_menu_page = current_url in menu_page_urls

                # --- Content Aggregation Strategy ---
                # Aggregate content into the MENU pool if it's a designated menu page
                # OR if it was specifically reached via an image link originating from a menu page.
                is_relevant_for_menu_items = is_primary_menu_page or is_image_linked_url

                if is_relevant_for_menu_items:
                     logger.info(f"{log_prefix} Merging content into MENU pool: {current_url}")
                     merge_content(menu_content_aggregated, content)
                     # Always merge into non-menu aggregate as well
                     merge_content(all_content_aggregated_non_menu, content)

                     # If it's a primary menu page, check its linked images for more URLs
                     if is_primary_menu_page:
                         for img_info in content.get('linked_image_info', []):
                             link_url = img_info.get('link_url')
                             if link_url and link_url not in processed_urls and link_url not in queue_to_process and link_url not in image_linked_urls_found:
                                  queue_to_process.append(link_url) # Add to the end of the main queue
                                  image_linked_urls_found.add(link_url) # Track it
                                  logger.info(f"{log_prefix} Added image-linked URL to queue: {link_url}")
                else:
                     # For other pages, only aggregate for non-menu info
                     logger.debug(f"{log_prefix} Merging content into NON-MENU pool ONLY: {current_url}")
                     merge_content(all_content_aggregated_non_menu, content)

                # --- Simplified Alt Text Aggregation ---
                # Add *all* alt text found on this page to the common pool
                alt_added_count = 0
                for img_info in content.get('linked_image_info', []):
                    alt = img_info.get('alt')
                    if alt:
                        aggregated_menu_alt_texts.add(alt)
                        alt_added_count += 1
                for alt_text in content.get('image_alt_texts', []):
                    if alt_text:
                        aggregated_menu_alt_texts.add(alt_text)
                        alt_added_count += 1
                if alt_added_count > 0:
                     logger.debug(f"{log_prefix} Added {alt_added_count} alt texts from page {current_url} to common pool.")

            # --- End scraping loop --- (REMOVE the queue switching logic here)

            # Add aggregated alt texts to the specific menu content dict
            final_alt_texts_list = list(aggregated_menu_alt_texts)
            menu_content_aggregated['image_alt_texts'] = final_alt_texts_list
            logger.info(f"Final aggregated alt text list size: {len(final_alt_texts_list)}. Examples: {final_alt_texts_list[:10]}")

            # Check if any content was aggregated
            if not menu_content_aggregated.get('all_text') and not all_content_aggregated_non_menu.get('all_text'): # Check both pools
                 logger.warning(f"No significant content could be aggregated for {url}")
                 return {}

            # --- Final Extraction ---
            logger.info(f"Starting final extraction for {url}")
            # Extract menu items ONLY from the dedicated menu content pool
            if menu_content_aggregated.get('all_text'): # Check if menu pool has content
                 logger.info(f"Extracting menu items from MENU content pool...")
                 menu_items = self._extract_menu_items(menu_content_aggregated)
            else:
                 logger.warning(f"MENU content pool is empty for {url}, no menu items extracted.")
                 menu_items = []

            # Extract other info from the general (non-menu) aggregated content pool
            # Ensure the dictionary exists even if empty for subsequent calls
            if not all_content_aggregated_non_menu:
                 all_content_aggregated_non_menu = { # Create structure if needed
                      'social_links': {},
                      'all_text': '',
                      # Add other keys expected by extract functions if necessary
                      'paragraphs': [], 'list_items': [], 'divs': [], 'headings': [], 'class_elements': [], 'meta_data': [], 'structured_data': [], 'table_data': [], 'spans': []
                 }

            restaurant_info = self._extract_restaurant_info(all_content_aggregated_non_menu)
            special_features = self._extract_special_features(all_content_aggregated_non_menu)
            operating_hours = self._extract_operating_hours(all_content_aggregated_non_menu)
            social_links = all_content_aggregated_non_menu.get('social_links', {})

            result = {
                "restaurant_info": restaurant_info,
                "menu_items": menu_items,
                "special_features": special_features,
                "operating_hours": operating_hours
            }
            
            # Add social media if present
            if social_links:
                result["social_media"] = social_links
                
            return result
        # Catch potential KeyErrors during extraction as a safety net, though .get should prevent them
        except KeyError as ke:
             logger.error(f"KeyError during extraction for {url}: {str(ke)}. Aggregated content might be incomplete due to fetch errors.")
             return {}
        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            logger.error(f"Error scraping {url}: {str(e)}\\nTraceback:\\n{tb_str}")
            return {}
            
    def scrape_restaurant_info(self, url: str) -> Dict:
        """Scrape basic restaurant information."""
        urls_to_scrape = self._find_relevant_pages(url)
        all_content = {}
        
        for page_url in urls_to_scrape:
            content = self._get_all_content(page_url)
            # Merge content
            for key, value in content.items():
                if key not in all_content:
                    all_content[key] = value
                elif isinstance(value, list):
                    all_content[key].extend(value)
                    
        return self._extract_restaurant_info(all_content)

    def scrape_menu(self, url: str) -> List[Dict]:
        """Scrape restaurant menu items."""
        urls_to_scrape = self._find_relevant_pages(url)
        all_content = {}
        
        for page_url in urls_to_scrape:
            if 'menu' in page_url.lower():  # Prioritize menu pages
                content = self._get_all_content(page_url)
                # Merge content
                for key, value in content.items():
                    if key not in all_content:
                        all_content[key] = value
                    elif isinstance(value, list):
                        all_content[key].extend(value)
                        
        return self._extract_menu_items(all_content)

    def scrape_special_features(self, url: str) -> Dict:
        """Scrape special features and dietary information."""
        urls_to_scrape = self._find_relevant_pages(url)
        all_content = {}
        
        for page_url in urls_to_scrape:
            content = self._get_all_content(page_url)
            # Merge content
            for key, value in content.items():
                if key not in all_content:
                    all_content[key] = value
                elif isinstance(value, list):
                    all_content[key].extend(value)
                    
        return self._extract_special_features(all_content)

    def scrape_operating_hours(self, url: str) -> Dict:
        """Scrape operating hours and contact information."""
        urls_to_scrape = self._find_relevant_pages(url)
        all_content = {}
        
        for page_url in urls_to_scrape:
            if any(keyword in page_url.lower() for keyword in ['hour', 'contact', 'about', 'location']):
                content = self._get_all_content(page_url)
                # Merge content
                for key, value in content.items():
                    if key not in all_content:
                        all_content[key] = value
                    elif isinstance(value, list):
                        all_content[key].extend(value)
                        
        return self._extract_operating_hours(all_content) 
    

            