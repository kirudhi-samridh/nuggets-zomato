from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class MenuItem(BaseModel):
    """Schema for menu items."""
    name: str
    description: str
    price: Any  # Allow any type for price (string, float, etc.)
    category: str
    dietary_info: Dict[str, bool] = Field(
        default_factory=lambda: {
            "vegetarian": False,
            "vegan": False,
            "gluten_free": False
        }
    )

class OperatingHours(BaseModel):
    """Schema for operating hours."""
    open: str
    close: str

class RestaurantInfo(BaseModel):
    """Schema for restaurant information."""
    name: str
    address: str
    phone: str
    email: Optional[str] = None
    website: Optional[str] = None
    cuisine: List[str] = Field(default_factory=list)

class SpecialFeatures(BaseModel):
    """Schema for special features."""
    delivery: bool = False
    takeout: bool = False
    reservations: bool = False
    outdoor_seating: bool = False
    wheelchair_accessible: bool = False
    parking: bool = False
    wifi: bool = False
    # Add new features detected by the scraper
    happy_hour: bool = False
    live_music: bool = False
    kids_friendly: bool = False
    alcohol_served: bool = False

class Restaurant(BaseModel):
    """Schema for complete restaurant data."""
    restaurant_info: RestaurantInfo
    menu_items: List[MenuItem] = Field(default_factory=list)
    operating_hours: Dict[str, OperatingHours] = Field(default_factory=dict)
    special_features: SpecialFeatures = Field(default_factory=SpecialFeatures)

class Document(BaseModel):
    """Schema for documents in the knowledge base."""
    id: str
    content: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None

class Query(BaseModel):
    """Schema for search queries."""
    text: str
    filters: Optional[Dict[str, Any]] = None
    limit: int = 5 