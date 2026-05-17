"""Pydantic models for OpenAI tool schemas."""
from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Dict, Any

class SearchPlacesRequest(BaseModel):
    """Search amenities from the local dataset."""
    category: Optional[str] = Field(None, description="OSM amenity tag, e.g. 'cafe'")
    near_lat: Optional[float] = Field(None, description="Latitude of anchor point")
    near_lon: Optional[float] = Field(None, description="Longitude of anchor point")
    max_distance_km: Optional[float] = Field(None, description="Maximum distance from anchor")
    limit: int = Field(default=10, description="Maximum number of results")


class RankPlacesRequest(BaseModel):
    """Rank a list of places by strategy."""
    places: List[Dict[str, Any]] = Field(..., description="List of place dictionaries")
    strategy: Literal["distance", "score"] = Field(
        ..., 
        description="Ranking strategy: 'distance' (ascending) or 'score' (composite)"
    )


class UnderservedAreasRequest(BaseModel):
    """Find grid cells where amenity is underrepresented."""
    category: str = Field(..., description="Amenity category, e.g. 'pharmacy'")
    top_k: int = Field(default=10, description="Number of top underserved cells to return")


class FilterRequest(BaseModel):
    """Filter places by category or rating."""
    places: List[Dict[str, Any]] = Field(..., description="List of places to filter")
    strategy: Literal["category", "rating"] = Field(
        default="rating",
        description="Filtering mode"
    )
    category: Optional[str] = Field(
        default=None,
        description="Required if strategy='category'"
    )
    min_rating: Optional[float] = Field(
        default=None,
        description="Required if strategy='rating'"
    )


class DistanceRequest(BaseModel):
    """Calculate distance between two points."""
    p1: List[float] = Field(
        ..., 
        min_length=2, 
        max_length=2,
        description="First point coordinates [lat, lon]"
    )
    p2: List[float] = Field(
        ..., 
        min_length=2, 
        max_length=2,
        description="Second point coordinates [lat, lon]"
    )


# Helper function to convert Pydantic model to OpenAI tool schema
def to_tool_schema(model_class: type[BaseModel], name: str, description: str) -> dict:
    """Convert Pydantic model to OpenAI-compatible tool schema."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": model_class.model_json_schema()
        }
    }


# Generate TOOLS from Pydantic models
TOOLS = [
    to_tool_schema(
        SearchPlacesRequest,
        "search_places",
        "Search amenities (cafe, restaurant, pharmacy, bar, ...) from the local dataset. Optionally filter by distance from an anchor point."
    ),
    to_tool_schema(
        RankPlacesRequest,
        "rank_places",
        "Rank a previously returned list of places. Strategy is either 'distance' (ascending distance_km) or 'score' (composite rating - distance)."
    ),
    to_tool_schema(
        UnderservedAreasRequest,
        "find_underserved_areas",
        "Find grid cells in the city where a given amenity category is underrepresented relative to overall POI density. Use for 'where is X missing' queries."
    ),
    to_tool_schema(
        FilterRequest,
        "filter_places",
        "Filters places by category or rating."
    ),
    to_tool_schema(
        DistanceRequest,
        "calculate_distance",
        "Calculate distance between two points. Returns number."
    ),
]