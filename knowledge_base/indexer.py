from typing import Dict, List, Optional
# import json # No longer needed
from pathlib import Path
# import uuid # LlamaIndex handles document IDs
from loguru import logger

# Remove transformers and torch imports
# from transformers import AutoTokenizer, AutoModel
# import torch

# LlamaIndex imports
from llama_index.core import (
    Document,
    VectorStoreIndex,
    StorageContext,
    load_index_from_storage,
    Settings,
)
from llama_index.core.embeddings import resolve_embed_model
from llama_index.core.schema import NodeWithScore
# Separate imports for clarity and potential resolution
from llama_index.core.vector_stores import VectorStoreQuery, ExactMatchFilter, MetadataFilters
# from llama_index.core import QueryMode # Try importing QueryMode from core # Removed QueryMode import
# Chroma specific imports
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb # Import the chromadb client library

from .schema import Restaurant # Keep your Restaurant schema if needed for input processing
# from .vector_store import VectorStore # Remove custom VectorStore import

# Default persistence directory (used by Chroma persistent client)
# Ensure STORAGE_DIR is defined correctly in config.py
DEFAULT_PERSIST_DIR = "./storage" 
DEFAULT_CHROMA_COLLECTION = "restaurant_kb" # Default Chroma collection name

class Indexer:
    """Manages the knowledge base indexing process using LlamaIndex and ChromaDB."""
    
    def __init__(self, config: Dict):
        self.config = config
        # self.vector_store = VectorStore(config) # Remove custom vector store
        self._index = None
        # Use persist_dir from config for Chroma path
        self.persist_dir = Path(config.get("persist_dir", DEFAULT_PERSIST_DIR))
        self.collection_name = config.get("chroma_collection", DEFAULT_CHROMA_COLLECTION)

        # --- LlamaIndex Settings --- 
        Settings.embed_model = resolve_embed_model("local:sentence-transformers/all-MiniLM-L6-v2")
        Settings.llm = None # Explicitly disable default LLM loading in LlamaIndex
        # Settings.chunk_size = 512 # Adjust chunk size if needed
        
        # --- ChromaDB Setup --- 
        logger.info(f"Initializing ChromaDB client at path: {self.persist_dir}")
        # Initialize ChromaDB client (persistent on disk)
        db = chromadb.PersistentClient(path=str(self.persist_dir))
        
        # Get or create the Chroma collection
        logger.info(f"Getting/creating Chroma collection: {self.collection_name}")
        chroma_collection = db.get_or_create_collection(self.collection_name)

        # --- LlamaIndex Storage Context Setup --- 
        # Create a LlamaIndex ChromaVectorStore instance
        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
        
        # Create the LlamaIndex StorageContext using the Chroma vector store
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        
        # --- Load or Initialize LlamaIndex Index --- 
        # Check if index already exists (by trying to load from the vector store)
        # Note: For Chroma, checking directory existence isn't enough.
        # We load the index directly from the configured storage context.
        try:
             logger.info(f"Attempting to load index from Chroma collection '{self.collection_name}'...")
             # Pass the specific storage_context (which uses Chroma) to load
             self._index = VectorStoreIndex.from_vector_store(
                 vector_store=vector_store,
                 storage_context=storage_context,
             )
             # A more robust check might involve checking if the index has nodes
             if self._index.docstore.docs:
                 logger.info("Index loaded successfully from Chroma.")
             else:
                 logger.info("Index loaded from Chroma, but appears empty. Will treat as new.")
                 # If empty, we might still want to create it fresh below, 
                 # though from_vector_store usually handles this.
                 # Let's assume from_vector_store gives a usable (even if empty) index.

        except Exception as e:
             # Many potential errors: collection empty, network issues if remote, etc.
             logger.warning(f"Could not load index directly from vector store ({e}). ", exc_info=True)
             logger.info("Initializing new index structure associated with the Chroma collection.")
             # If loading fails, create a new index structure linked to the vector store
             self._index = VectorStoreIndex.from_documents(
                 [], # Start empty, documents will be inserted
                 storage_context=storage_context,
             )
        
        # Ensure we always have an index object
        if self._index is None:
             logger.error("Failed to load or initialize index! Check Chroma setup and logs.")
             # Handle this critical failure appropriately, maybe raise an error
             # For now, creating a fallback in-memory index (NOT ideal)
             # self._index = VectorStoreIndex.from_documents([])
             raise RuntimeError("Failed to establish connection with vector store index.")

    # Remove manual model/tokenizer loading properties
    # @property
    # def model(self): ...
    # @property
    # def tokenizer(self): ...

    # Remove manual embedding generation
    # def _generate_embedding(self, text: str) -> List[float]: ...

    @property
    def index(self) -> VectorStoreIndex:
        """Get the LlamaIndex index instance."""
        if self._index is None:
            logger.error("Index accessed before initialization!")
            raise RuntimeError("Index not initialized.") # Make failure explicit
        return self._index

    def _create_llama_documents(self, restaurant: Restaurant) -> List[Document]:
        """Create LlamaIndex Document objects from restaurant data."""
        llama_docs = []
        restaurant_id = restaurant.restaurant_info.name # Use a consistent ID
        restaurant_id_lower = restaurant_id.lower() # Add lowercase version for case-insensitive matching
        
        # Create document for restaurant info
        info_text = f"""
        Restaurant: {restaurant.restaurant_info.name}
        Address: {restaurant.restaurant_info.address}
        Phone: {restaurant.restaurant_info.phone}
        Cuisine: {', '.join(restaurant.restaurant_info.cuisine)}
        """
        # LlamaIndex Document requires text and optional metadata
        llama_docs.append(Document(
            text=info_text,
            metadata={
                "doc_type": "restaurant_info", # Renamed 'type' to avoid potential conflicts
                "restaurant_id": restaurant_id,
                "restaurant_id_lower": restaurant_id_lower # Add lowercase version for matching
            },
            # embedding is handled by LlamaIndex
        ))
        
        # Create documents for menu items
        for item in restaurant.menu_items:
            # Construct item text conditionally
            item_text_parts = [f"Item: {item.name}"]
            if item.description:
                 item_text_parts.append(f"Description: {item.description}")
            if item.price > 0.0: 
                 item_text_parts.append(f"Price: ${item.price:.2f}")
            if item.category:
                 item_text_parts.append(f"Category: {item.category}")
            
            dietary_parts = [k for k, v in item.dietary_info.items() if v]
            if dietary_parts:
                 item_text_parts.append(f"Dietary: {', '.join(dietary_parts)}")
            
            item_text = "\n".join(item_text_parts)
            
            if not item_text.strip():
                 logger.warning(f"Skipping menu item document creation for '{item.name}' in '{restaurant_id}' due to empty text.")
                 continue

            # --- Add dietary info to metadata --- 
            # Use the results from the data processor (which should be booleans)
            is_vegetarian = item.dietary_info.get("vegetarian", False)
            is_vegan = item.dietary_info.get("vegan", False)
            is_gluten_free = item.dietary_info.get("gluten_free", False)
            
            # Log the dietary info for debugging
            logger.debug(f"Menu item '{item.name}' dietary info: vegetarian={is_vegetarian}, vegan={is_vegan}, gluten_free={is_gluten_free}")
            
            item_metadata = {
                "doc_type": "menu_item",
                "restaurant_id": restaurant_id,
                "restaurant_id_lower": restaurant_id_lower, # Add lowercase version for matching
                "category": item.category or "Uncategorized",
                "item_name": item.name,
                # Store dietary flags as strings for filtering
                "vegetarian": str(is_vegetarian).lower(), # "true" or "false"
                "vegan": str(is_vegan).lower(),
                "gluten_free": str(is_gluten_free).lower()
            }

            llama_docs.append(Document(
                text=item_text,
                metadata=item_metadata,
            ))
        
        return llama_docs
    
    def index_restaurant(self, restaurant: Restaurant):
        """Index a restaurant using LlamaIndex."""
        try:
            llama_documents = self._create_llama_documents(restaurant)
            if not llama_documents:
                 logger.warning(f"No documents generated for restaurant: {restaurant.restaurant_info.name}")
                 return

            logger.debug(f"Inserting {len(llama_documents)} documents for {restaurant.restaurant_info.name} into Chroma...")
            # LlamaIndex insert handles adding to the configured vector store (Chroma)
            for doc in llama_documents:
                self.index.insert(doc)
            
            logger.info(f"Indexed restaurant: {restaurant.restaurant_info.name}")
            # Optional: Persist LlamaIndex specific metadata (may not be needed if Chroma is primary store)
            # self.save() 

        except Exception as e:
            logger.exception(f"Error indexing restaurant {restaurant.restaurant_info.name}: {str(e)}")
    
    def index_restaurants(self, restaurants: List[Restaurant]):
        """Index multiple restaurants in the knowledge base."""
        count = 0
        total = len(restaurants)
        for restaurant in restaurants:
            count += 1
            logger.info(f"Indexing restaurant {count}/{total}: {restaurant.restaurant_info.name}")
            self.index_restaurant(restaurant)
        logger.info("Finished indexing all restaurants.")
    
    def search(self, query_text: str, filters: Optional[Dict] = None, limit: int = 5) -> List[NodeWithScore]:
        """Search the knowledge base using a direct vector store query for better filtering."""
        try:
            # Build LlamaIndex metadata filters from the input dict
            llama_filters = None
            if filters:
                filter_list = []
                for key, value in filters.items():
                    filter_list.append(ExactMatchFilter(key=key, value=value))
                if filter_list:
                    llama_filters = MetadataFilters(filters=filter_list)
            
            logger.debug(f"Indexer searching Chroma with query: '{query_text}', limit: {limit}, filters: {llama_filters}")
            
            # Create a VectorStoreQuery object
            vector_store_query = VectorStoreQuery(
                query_str=query_text, # Use query_str for text queries
                similarity_top_k=limit,
                # mode=QueryMode.DEFAULT, # Removed unnecessary 'mode' parameter
                filters=llama_filters # Apply filters directly
            )
            
            # Query the vector store directly via the index
            # The index object holds a reference to the configured vector store
            query_result = self.index.vector_store.query(vector_store_query)
            
            if query_result and query_result.nodes:
                 logger.debug(f"Retrieved {len(query_result.nodes)} nodes from vector store query.")
                 return query_result.nodes
            else:
                 logger.warning(f"No nodes returned from vector store query for query: '{query_text}' with filters: {filters}")
                 return []

        except Exception as e:
            logger.exception(f"Error searching knowledge base: {str(e)}")
            return []
    
    # Remove the save method, as persistence is handled by ChromaClient
    # def save(self):
    #     """Save the LlamaIndex index to disk.""" # No longer needed
    #     try:
    #          logger.info(f"Persisting index to: {self.persist_dir}")
    #          # Chroma persists automatically via the client
    #          # self.index.storage_context.persist(persist_dir=str(self.persist_dir))
    #          logger.info("Index persistence handled by ChromaDB.")
    #     except Exception as e:
    #          logger.exception(f"Error during (now potentially obsolete) index save call: {str(e)}")

    # Load is handled in __init__
    # def load(self, directory: Path): ... 