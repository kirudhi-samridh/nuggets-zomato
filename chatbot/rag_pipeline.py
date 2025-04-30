from typing import Dict, List, Optional, Tuple, Any
from loguru import logger
import re

from .retriever import Retriever
from .generator import Generator
from .query_processor import QueryProcessor
# from knowledge_base.schema import Query # No longer needed for input type
from knowledge_base.schema import Document # Keep for context formatting

class RAGPipeline:
    """Pipeline that combines retrieval and generation with query decomposition."""
    
    def __init__(self, retriever: Retriever, generator: Generator, groq_api_key: Optional[str] = None):
        self.retriever = retriever
        self.generator = generator
        self.query_processor = QueryProcessor(groq_api_key)
    
    def process_query(self, query_text: str, filters: Optional[Dict] = None) -> str:
        """Process a query through the RAG pipeline with query decomposition support."""
        try:
            # Check if the query needs decomposition (complex query mentioning multiple restaurants)
            sub_queries = self._check_decomposition(query_text, filters)
            
            if len(sub_queries) > 1:
                # Process each sub-query and combine results
                return self._process_multiple_queries(sub_queries)
            else:
                # Process single query
                return self._process_single_query(query_text, filters)
                
        except Exception as e:
            logger.exception(f"Error in RAG pipeline: {str(e)}") # Use logger.exception
            return "I apologize, but I'm having trouble processing your question at the moment."
    
    def _check_decomposition(self, query_text: str, filters: Optional[Dict] = None) -> List[Tuple[str, Optional[Dict]]]:
        """Check if query needs decomposition and decompose if necessary."""
        # If we detect complex query patterns, decompose the query
        if ("and" in query_text.lower() and 
            any(term in query_text.lower() for term in ["in", "at", "from", "restaurant"])):
            
            # Use the query processor to decompose the query
            sub_queries = self.query_processor.process_query(query_text)
            
            if len(sub_queries) > 1:
                logger.info(f"Decomposed complex query into {len(sub_queries)} sub-queries")
                return sub_queries
        
        # If no decomposition needed or decomposition failed, just return original query with filters
        return [(query_text, filters)]
    
    def _process_single_query(self, query_text: str, filters: Optional[Dict] = None) -> str:
        """Process a single query through the RAG pipeline."""
        # Pass filters to the retriever
        documents = self.retriever.retrieve(query_text, filters=filters)
        
        if not documents:
            # Use the original query text in the message
            logger.warning(f"No documents found for query: '{query_text}' with filters: {filters}")
            return "I couldn't find any relevant information to answer your question."
        
        # Format context from retrieved documents
        context = self.retriever.format_context(documents)
        
        # Generate response using the original query text
        prompt = self.generator.format_prompt(query_text, context)
        response = self.generator.generate(prompt)
        
        return response
    
    def _process_multiple_queries(self, sub_queries: List[Tuple[str, Optional[Dict]]]) -> str:
        """Process multiple sub-queries and combine the results."""
        results = []
        
        for query_text, filters in sub_queries:
            # Process each sub-query
            result = self._process_single_query(query_text, filters)
            results.append((query_text, result))
        
        # Combine the results
        return self._combine_results(results)
    
    def _combine_results(self, results: List[Tuple[str, str]]) -> str:
        """Combine results from multiple sub-queries into a coherent response."""
        combined = "Here's what I found:\n\n"
        
        for query, result in results:
            # Extract the query subject for section heading
            section_title = self._extract_section_title(query)
            combined += f"**{section_title}**\n{result}\n\n"
        
        return combined
    
    def _extract_section_title(self, query: str) -> str:
        """Extract a section title from a query."""
        # Try to extract restaurant name
        restaurant_patterns = [
            r'in\s+([\w\s\']+)', 
            r'at\s+([\w\s\']+)', 
            r'from\s+([\w\s\']+)',
            r'([\w\s\']+)\s+restaurant',
            r'([\w\s\']+)\s+menu'
        ]
        
        for pattern in restaurant_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                restaurant = match.group(1).strip()
                if restaurant:
                    # Also try to extract the query type (veg, non-veg, etc.)
                    for food_type in ["vegetarian", "veg", "non-veg", "non vegetarian"]:
                        if food_type in query.lower():
                            return f"{food_type.title()} options from {restaurant.title()}"
                    return f"Options from {restaurant.title()}"
        
        # Fallback to using the query itself
        if len(query) > 40:
            return query[:37] + "..."
        return query
    
    # process_queries might need adjustment depending on how it's used
    # If it takes a list of strings now, update accordingly
    # def process_queries(self, queries: List[str]) -> List[str]:
    #     """Process multiple query strings through the RAG pipeline."""
    #     return [self.process_query(query) for query in queries] 