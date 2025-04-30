from typing import Dict, List, Optional
from loguru import logger
import re
import difflib # For fuzzy restaurant name matching

from knowledge_base.indexer import Indexer
# from knowledge_base.schema import Document # Use LlamaIndex Node instead
from llama_index.core.schema import NodeWithScore, TextNode # Import both types

DEFAULT_SEARCH_LIMIT = 5

class Retriever:
    """Retrieves relevant documents (nodes) from the knowledge base."""
    
    def __init__(self, indexer: Indexer, kb_config: Dict):
        self.indexer = indexer
        # Get limit from config, falling back to default
        self.search_limit = kb_config.get("search_limit", DEFAULT_SEARCH_LIMIT)
        logger.info(f"Retriever initialized with search_limit: {self.search_limit}")
        
        # Load list of known restaurants from the index
        self.known_restaurants = self._get_known_restaurants()
        
    def _get_known_restaurants(self) -> List[str]:
        """Get a list of all restaurant names in the index for fuzzy matching."""
        try:
            # Special search to get all distinct restaurants
            query_result = self.indexer.search(
                "", # Empty query
                filters={"doc_type": "restaurant_info"},
                limit=100 # Get up to 100 restaurants
            )
            
            restaurants = []
            for doc in query_result:
                node = doc.node if hasattr(doc, 'node') else doc
                if hasattr(node, 'metadata') and 'restaurant_id' in node.metadata:
                    restaurants.append(node.metadata['restaurant_id'].lower())
            
            if restaurants:
                logger.info(f"Loaded {len(restaurants)} known restaurants from index")
            else:
                # Fallback list if no restaurants found in index
                restaurants = [
                    "smokin joes pizza", 
                    "thalappakatti", 
                    "kailash parbat",
                    "flurys",
                    "paakashala"
                ]
                logger.warning(f"No restaurants found in index, using default list of {len(restaurants)} restaurants")
                
            return restaurants
            
        except Exception as e:
            logger.error(f"Error retrieving restaurant list: {str(e)}")
            # Return a default list
            return [
                "smokin joes pizza", 
                "thalappakatti", 
                "kailash parbat",
                "flurys",
                "paakashala"
            ]
    
    def _fuzzy_match_restaurant(self, name: str, threshold: float = 0.7) -> Optional[str]:
        """Find the closest matching restaurant using fuzzy string matching."""
        if not name or not self.known_restaurants:
            return None
            
        # First try direct substring matching
        for restaurant in self.known_restaurants:
            if restaurant in name.lower() or name.lower() in restaurant:
                logger.info(f"Direct substring match: '{name}' contains or is contained in '{restaurant}'")
                return restaurant
                
        # If no direct match, try fuzzy matching
        matches = difflib.get_close_matches(name.lower(), self.known_restaurants, n=1, cutoff=threshold)
        if matches:
            logger.info(f"Fuzzy matched '{name}' to '{matches[0]}' with threshold {threshold}")
            return matches[0]
            
        # If still no match, try a more lenient threshold
        if threshold > 0.5:
            return self._fuzzy_match_restaurant(name, threshold=0.5)
            
        return name
    
    def retrieve(self, query_text: str, filters: Optional[Dict] = None) -> List:
        """Retrieve relevant LlamaIndex nodes for a query string, applying filters."""
        try:
            # Process special flags in filters
            modified_filters = {}
            want_distinct = False
            
            if filters:
                # Make a copy to avoid modifying the original
                modified_filters = filters.copy()
                
                # Check for and remove special flags
                if "distinct" in modified_filters:
                    want_distinct = modified_filters.pop("distinct") == "true"
                
                # Also check query text for distinct keyword
                want_distinct = want_distinct or "distinct" in query_text.lower()
                
                # Apply fuzzy matching to restaurant name if present
                if "restaurant_id_lower" in modified_filters:
                    restaurant_name = modified_filters["restaurant_id_lower"]
                    matched_name = self._fuzzy_match_restaurant(restaurant_name)
                    if matched_name and matched_name != restaurant_name:
                        logger.info(f"Using fuzzy-matched restaurant name: '{matched_name}' instead of '{restaurant_name}'")
                        modified_filters["restaurant_id_lower"] = matched_name
            
            # If distinct items are requested, increase the limit to ensure we have enough after filtering
            search_limit = self.search_limit * 3 if want_distinct else self.search_limit
            
            # Search the knowledge base using the text, configured limit, and passed filters
            logger.debug(f"Retriever searching with query: '{query_text}', limit: {search_limit}, filters: {modified_filters}, distinct_items: {want_distinct}")
            documents = self.indexer.search(
                query_text,
                filters=modified_filters,
                limit=search_limit
            )
            
            # If no results but we have a restaurant filter, try fallback strategies
            if not documents and modified_filters and "restaurant_id_lower" in modified_filters:
                documents = self._try_fallback_search(query_text, modified_filters, search_limit)
            
            if not documents:
                logger.warning(f"No documents found for query: {query_text} with filters: {modified_filters}")
                return []
            
            # Filter for distinct items if needed
            if want_distinct and documents:
                distinct_docs = self._filter_distinct_items(documents)
                # Ensure we don't exceed the original limit
                distinct_docs = distinct_docs[:self.search_limit]
                logger.info(f"Filtered {len(documents)} documents to {len(distinct_docs)} distinct items")
                return distinct_docs
            
            return documents
        except Exception as e:
            logger.exception(f"Error retrieving documents: {str(e)}")
            return []
    
    def _try_fallback_search(self, query_text: str, filters: Dict, limit: int) -> List:
        """Try multiple fallback strategies when an exact match fails."""
        logger.info(f"Attempting fallback search strategies for query: '{query_text}'")
        
        # Strategy 1: Try with just the first word of restaurant name
        restaurant_name = filters.get("restaurant_id_lower", "")
        if restaurant_name and " " in restaurant_name:
            first_word = restaurant_name.split()[0]
            fallback_filters = filters.copy()
            fallback_filters["restaurant_id_lower"] = first_word
            
            logger.info(f"Fallback strategy 1: Using first word of restaurant name: '{first_word}'")
            documents = self.indexer.search(
                query_text,
                filters=fallback_filters,
                limit=limit
            )
            
            if documents:
                logger.info(f"Fallback strategy 1 succeeded with {len(documents)} results")
                return documents
        
        # Strategy 2: Remove restaurant filter but add restaurant name to query
        if restaurant_name:
            fallback_filters = {k: v for k, v in filters.items() if k != "restaurant_id_lower"}
            enhanced_query = f"{query_text} {restaurant_name}"
            
            logger.info(f"Fallback strategy 2: Removing restaurant filter and enhancing query with restaurant name")
            documents = self.indexer.search(
                enhanced_query,
                filters=fallback_filters,
                limit=limit
            )
            
            if documents:
                logger.info(f"Fallback strategy 2 succeeded with {len(documents)} results")
                return documents
        
        # Strategy 3: Keep only dietary filters
        dietary_filters = {}
        for key in ["vegetarian", "vegan", "gluten_free"]:
            if key in filters:
                dietary_filters[key] = filters[key]
        
        if dietary_filters:
            dietary_filters["doc_type"] = "menu_item"
            logger.info(f"Fallback strategy 3: Using only dietary filters: {dietary_filters}")
            documents = self.indexer.search(
                query_text,
                filters=dietary_filters,
                limit=limit
            )
            
            if documents:
                logger.info(f"Fallback strategy 3 succeeded with {len(documents)} results")
                return documents
        
        # Strategy 4: Last resort - use only doc_type filter
        logger.info(f"Fallback strategy 4: Using only doc_type filter")
        documents = self.indexer.search(
            query_text,
            filters={"doc_type": "menu_item"},
            limit=limit
        )
        
        if documents:
            logger.info(f"Fallback strategy 4 succeeded with {len(documents)} results")
        
        return documents
    
    def _filter_distinct_items(self, documents: List) -> List:
        """Filter documents to return only distinct items (removing size variations)."""
        distinct_items = {}
        size_keywords = ['small', 'medium', 'large', 'regular', 'jumbo', 'mini', 'maha', 'half', 'full']
        
        for doc in documents:
            # Get the node object
            node = doc.node if hasattr(doc, 'node') else doc
            
            if not hasattr(node, 'metadata'):
                # Skip nodes without metadata
                continue
                
            # Get item name
            item_name = node.metadata.get('item_name', '')
            if not item_name:
                continue
                
            # Remove size terms to get base name
            base_name = item_name
            for size in size_keywords:
                # Replace size at end or in the middle of name
                base_name = re.sub(r'\b' + size + r'\b', '', base_name, flags=re.IGNORECASE)
            
            # Clean up extra spaces
            base_name = ' '.join(base_name.split()).strip()
            
            # Skip if empty after cleaning
            if not base_name:
                continue
                
            # Keep track of distinct items by base name
            if base_name not in distinct_items:
                distinct_items[base_name] = doc
                logger.debug(f"Adding distinct item: '{item_name}' with base name: '{base_name}'")
        
        return list(distinct_items.values())
    
    def format_context(self, documents: List) -> str:
        """Format retrieved LlamaIndex nodes into a context string."""
        if not documents:
            return ""
        
        context_parts = []
        for node in documents:
            # Handle either NodeWithScore or TextNode directly
            # First determine what type of node we have
            if hasattr(node, 'node'):
                # It's a NodeWithScore wrapper
                doc = node.node
            else:
                # It's already a TextNode or similar
                doc = node
                
            # Add debugging to see what we're working with
            logger.debug(f"Processing node: type={type(doc)}, id={getattr(doc, 'id_', 'unknown')}")
            
            # Add document text content
            if hasattr(doc, 'text'):
                context_parts.append(doc.text)
            elif hasattr(doc, 'get_content'):
                context_parts.append(doc.get_content())
            
            # Add metadata if relevant
            if hasattr(doc, 'metadata') and doc.metadata.get("doc_type") == "menu_item":
                # Extract relevant metadata for context
                category = doc.metadata.get('category', 'Unknown')
                item_name = doc.metadata.get('item_name', doc.metadata.get('name', 'Unknown Item'))
                # Add other relevant metadata like price if available in the node metadata
                context_parts.append(
                    f"Item: {item_name} (Category: {category})" 
                    # Potentially add price or other details if stored in metadata
                )
        
        return "\n\n".join(context_parts) 