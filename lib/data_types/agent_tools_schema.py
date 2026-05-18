"""Pydantic models for OpenAI tool schemas."""
from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Dict, Any
from lib.data_types import Place

class SearchPlacesRequest(BaseModel):
    """Search amenities from the local dataset."""
    category: Optional[list[str]] = Field(None, description="OSM list of amenity tags, e.g. ['cafe', 'restaurant'] etc. None = any")
    name: Optional[str] = Field(None, description="OSM name amenity, e.g. 'PizzaHut', 'Starbucks'")
    near_lat: Optional[float] = Field(None, description="Latitude of anchor point")
    near_lon: Optional[float] = Field(None, description="Longitude of anchor point")
    max_distance_km: Optional[float] = Field(None, description="Maximum distance from anchor")
    limit: int = Field(default=10, description="Maximum number of results")


class RankPlacesRequest(BaseModel):
    """Rank a list of places by strategy."""
    places: List[Place] = Field(..., description="List of place dictionaries")
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
    places: List[Place] = Field(..., description="List of places to filter")
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
