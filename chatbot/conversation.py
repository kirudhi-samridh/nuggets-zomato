from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import uuid
from loguru import logger
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

@dataclass
class Message:
    """Represents a message in the conversation."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = datetime.now()

class Conversation:
    """Manages conversation history and context using MongoDB."""
    
    def __init__(self, max_history: int = 5, mongo_uri: str = "mongodb://localhost:27017"):
        self.max_history = max_history
        self.messages: List[Message] = []
        self.chat_id = str(uuid.uuid4())
        
        # Initialize MongoDB connection
        try:
            self.client: MongoClient = MongoClient(mongo_uri)
            self.db: Database = self.client["restaurant_chatbot"]
            self.collection: Collection = self.db["conversations"]
            # Test connection
            self.client.server_info()
            logger.info("Successfully connected to MongoDB")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise
    
    def add_message(self, role: str, content: str):
        """Add a message to the conversation history and MongoDB."""
        message = Message(role=role, content=content)
        self.messages.append(message)
        
        # Trim history if it exceeds max_history
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]
        
        # Save to MongoDB
        try:
            self.collection.update_one(
                {"chat_id": self.chat_id},
                {
                    "$push": {
                        "messages": {
                            "role": message.role,
                            "content": message.content,
                            "timestamp": message.timestamp
                        }
                    }
                },
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error saving message to MongoDB: {str(e)}")
    
    def get_history(self) -> List[Message]:
        """Get the conversation history from MongoDB."""
        try:
            chat_data = self.collection.find_one({"chat_id": self.chat_id})
            if chat_data and "messages" in chat_data:
                self.messages = [
                    Message(
                        role=msg["role"],
                        content=msg["content"],
                        timestamp=msg["timestamp"]
                    )
                    for msg in chat_data["messages"]
                ]
        except Exception as e:
            logger.error(f"Error retrieving messages from MongoDB: {str(e)}")
        
        return self.messages
    
    def get_context(self) -> str:
        """Get the conversation context as a formatted string."""
        context_parts = []
        for message in self.messages:
            role = "User" if message.role == "user" else "Assistant"
            context_parts.append(f"{role}: {message.content}")
        
        return "\n".join(context_parts)
    
    def clear(self):
        """Clear the conversation history from both memory and MongoDB."""
        self.messages = []
        try:
            self.collection.delete_one({"chat_id": self.chat_id})
        except Exception as e:
            logger.error(f"Error clearing conversation from MongoDB: {str(e)}")
    
    def to_dict(self) -> Dict:
        """Convert conversation to dictionary format."""
        return {
            "chat_id": self.chat_id,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat()
                }
                for msg in self.messages
            ]
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Conversation':
        """Create a conversation from dictionary format."""
        conversation = cls()
        conversation.chat_id = data.get("chat_id", str(uuid.uuid4()))
        for msg_data in data.get("messages", []):
            conversation.add_message(
                role=msg_data["role"],
                content=msg_data["content"]
            )
        return conversation
    
    def __del__(self):
        """Clean up MongoDB connection."""
        try:
            self.client.close()
        except Exception as e:
            logger.error(f"Error closing MongoDB connection: {str(e)}") 