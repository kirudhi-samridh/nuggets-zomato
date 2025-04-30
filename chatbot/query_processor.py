from typing import Dict, List, Optional, Tuple
from loguru import logger
import re
import json

# Import for LLM integration
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    logger.warning("Groq not installed, using rule-based fallback for query decomposition")
    GROQ_AVAILABLE = False

class QueryDecomposer:
    """Handles decomposition of complex queries into simpler sub-queries using LLM."""
    
    def __init__(self, groq_api_key: Optional[str] = None):
        """Initialize with optional API key for Groq."""
        self.groq_api_key = groq_api_key
        self.groq_client = None
        
        # Initialize Groq client if available
        if GROQ_AVAILABLE and groq_api_key:
            try:
                self.groq_client = Groq(api_key=groq_api_key)
                logger.info("Groq client initialized for query decomposition")
            except Exception as e:
                logger.error(f"Failed to initialize Groq client: {str(e)}")
        
    def decompose_query(self, query_text: str) -> List[str]:
        """Decompose a complex query into multiple simpler queries."""
        # Try LLM-based decomposition first if available
        if self.groq_client:
            try:
                decomposed_queries = self._llm_decompose(query_text)
                if decomposed_queries:
                    return decomposed_queries
            except Exception as e:
                logger.error(f"LLM-based decomposition failed: {str(e)}, falling back to rule-based")
        
        # Fall back to rule-based decomposition
        return self._rule_based_decompose(query_text)
    
    def _llm_decompose(self, query_text: str) -> List[str]:
        """Use LLM to decompose complex queries."""
        if not self.groq_client:
            return []
            
        # Define the prompt for query decomposition
        prompt = f"""
        Decompose the following complex restaurant query into separate independent queries.
        Return the answer as a JSON array of query strings, with each query focused on a single restaurant.
        
        Query: {query_text}
        
        Example:
        For "give me 5 veg options in smokin joes pizza and 5 non veg options in thalappakatti", return:
        ["give me 5 veg options in smokin joes pizza", "give me 5 non veg options in thalappakatti"]
        
        Output JSON:
        """
        
        try:
            # Call the LLM API
            response = self.groq_client.chat.completions.create(
                model="llama2-70b-4096",  # lightweight model
                messages=[
                    {"role": "system", "content": "You decompose complex restaurant queries into simple queries. Respond with JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,  # deterministic output
                max_tokens=200
            )
            
            # Extract the response content
            result = response.choices[0].message.content.strip()
            
            # Try to parse JSON output
            try:
                # Clean up the response to handle potential prefix/suffix text
                json_start = result.find('[')
                json_end = result.rfind(']') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = result[json_start:json_end]
                    queries = json.loads(json_str)
                    
                    # Validate the result
                    if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
                        logger.info(f"LLM decomposed query into {len(queries)} sub-queries")
                        return queries
            except json.JSONDecodeError:
                logger.error(f"Failed to parse LLM response as JSON: {result}")
                
        except Exception as e:
            logger.error(f"Error calling Groq API: {str(e)}")
            
        return []
    
    def _rule_based_decompose(self, query_text: str) -> List[str]:
        """Fallback rule-based approach to decompose queries."""
        # Simple pattern matching to split queries with "and" between restaurant mentions
        restaurant_patterns = [
            r'in\s+([\w\s\']+?)\s+restaurant',  # "in X restaurant"
            r'at\s+([\w\s\']+?)\s+restaurant',  # "at X restaurant"
            r'from\s+([\w\s\']+?)\s+restaurant',  # "from X restaurant"
            r'in\s+([\w\s\']+?)(?:\s+and|\s+[,.]|\s*$)',  # "in X and"
            r'at\s+([\w\s\']+?)(?:\s+and|\s+[,.]|\s*$)',  # "at X,"
            r'from\s+([\w\s\']+?)(?:\s+and|\s+[,.]|\s*$)',  # "from X"
            r'([\w\s\']+?)\s+restaurant',  # "X restaurant"
            r'([\w\s\']+?)\s+menu'  # "X menu"
        ]
        
        # Look for phrases like "X options in RESTAURANT_A and Y options in RESTAURANT_B"
        and_split_pattern = r'(.*\b(?:in|at|from)\s+[\w\s\']+)(?:\s+and\s+)(.*\b(?:in|at|from)\s+[\w\s\']+)'
        
        # Try to split on "and" connecting two restaurant phrases
        match = re.search(and_split_pattern, query_text, re.IGNORECASE)
        if match:
            part1 = match.group(1).strip()
            part2 = match.group(2).strip()
            
            # Ensure each part has a complete query structure
            # If part2 doesn't start with a query verb like "give me", "show", etc.
            # prepend part1's query structure to it
            query_verbs = ["give", "show", "list", "tell", "what", "I want", "get"]
            has_query_verb = any(part2.lower().startswith(verb.lower()) for verb in query_verbs)
            
            if not has_query_verb:
                # Extract the query verb from part1
                verb_match = re.match(r'((?:give|show|list|tell|what|I want|get)(?:\s+\w+){0,3})', part1, re.IGNORECASE)
                if verb_match:
                    query_prefix = verb_match.group(1)
                    part2 = f"{query_prefix} {part2}"
            
            logger.info(f"Rule-based decomposition split query into: ['{part1}', '{part2}']")
            return [part1, part2]
        
        # If we can't split, return the original query
        return [query_text]

class QueryProcessor:
    """Process user queries for the restaurant chatbot."""
    
    def __init__(self, groq_api_key: Optional[str] = None):
        """Initialize query processor with optional LLM integration."""
        self.decomposer = QueryDecomposer(groq_api_key)
        
    def process_query(self, query_text: str) -> List[Tuple[str, Optional[Dict]]]:
        """
        Process and decompose the query, extracting filters for each sub-query.
        
        Returns a list of tuples: (sub_query, filters)
        """
        # Step 1: Decompose complex query into simpler sub-queries
        sub_queries = self.decomposer.decompose_query(query_text)
        
        # If no decomposition occurred, use the original query
        if not sub_queries:
            sub_queries = [query_text]
        
        # For logging
        if len(sub_queries) > 1:
            logger.info(f"Decomposed query into {len(sub_queries)} sub-queries: {sub_queries}")
        
        # Step 2: Process each sub-query separately
        results = []
        for sub_query in sub_queries:
            # Import here to avoid circular imports
            from ui.streamlit_app import parse_query_for_filters
            
            # Extract filters for this sub-query
            filters = parse_query_for_filters(sub_query)
            results.append((sub_query, filters))
        
        return results 