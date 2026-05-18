"""Pydantic models for OpenAI tool schemas."""
from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Dict, Any
from lib.data_types import Place

class SearchPlacesRequest(BaseModel):
    """Search amenities from the local dataset with optional geo-filter."""
    category: list[str] = Field(
        default_factory=list,
        description="OSM amenity tags, e.g. ['cafe','restaurant']. Empty = any.",
    )
    name: Optional[str] = Field(
        None, description="Substring/fuzzy of amenity name, e.g. 'Starbucks'."
    )
    near_lat: Optional[float] = Field(None, description="Anchor latitude.")
    near_lon: Optional[float] = Field(None, description="Anchor longitude.")
    max_distance_km: Optional[float] = Field(
        None, description="Keep only places within this radius of the anchor."
    )
    limit: int = Field(10, ge=1, description="Max results.")


class NearestPlacesRequest(BaseModel):
    """Find the N nearest amenities to a point. Anchor is REQUIRED."""
    near_lat: float = Field(..., description="Anchor latitude (required).")
    near_lon: float = Field(..., description="Anchor longitude (required).")
    category: list[str] = Field(
        default_factory=list, description="OSM amenity tags. Empty = any."
    )
    limit: int = Field(5, ge=1, description="How many nearest to return.")


class SearchByNameRequest(BaseModel):
    """Search amenities by name. `name` is REQUIRED."""
    name: str = Field(..., description="Amenity name to fuzzy-match (required).")
    near_lat: Optional[float] = Field(None, description="Optional anchor lat.")
    near_lon: Optional[float] = Field(None, description="Optional anchor lon.")


class RankPlacesRequest(BaseModel):
    """Rank places returned by a previous search tool."""
    places: List[Place] = Field(
        ...,
        description="Output list from a previous search/filter tool. "
                    "Pass it through unchanged; do NOT invent entries.",
    )
    strategy: Literal["distance", "score"] = Field(
        ..., description="'distance' = nearest first; 'score' = composite."
    )


class UnderservedAreasRequest(BaseModel):
    """Find grid cells where an amenity category is underrepresented."""
    category: list[str] = Field(
        ...,
        description="Amenity tags, e.g. ['pharmacy']. List for consistency "
                    "with search tools (one concept = one type everywhere).",
    )
    top_k: int = Field(10, ge=1, description="How many top cells to return.")


class FilterRequest(BaseModel):
    """Filter places returned by a previous search tool."""
    places: List[Place] = Field(
        ..., description="Output from a previous tool; pass unchanged."
    )
    strategy: Literal["category", "rating"] = Field(
        "rating", description="Filter mode."
    )
    category: Optional[list[str]] = Field(
        None, description="Required if strategy='category'. List of amenity tags."
    )
    min_rating: Optional[float] = Field(
        None, ge=0, le=5, description="Required if strategy='rating'."
    )


class DistanceRequest(BaseModel):
    """Great-circle distance between two [lat, lon] points, in km."""
    p1: List[float] = Field(..., min_length=2, max_length=2,
                            description="[lat, lon] of first point.")
    p2: List[float] = Field(..., min_length=2, max_length=2,
                            description="[lat, lon] of second point.")


class HeatmapRequest(BaseModel):
    """Build an HTML heat map from weighted points; returns a file path."""
    points: List[List[float]] = Field(
        ...,
        description="List of [lat, lon] or [lat, lon, weight]. Min 1 point.",
    )
    radius: int = Field(12, ge=1, description="Heat point radius (px).")
    legend: bool = Field(False, description="Show a legend overlay.")


# Helper function to convert Pydantic model to OpenAI tool schema
def to_tool_schema(model_class: type[BaseModel], name: str, description: str) -> dict:
    """Convert Pydantic model to OpenAI-compatible tool schema."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": model_class.model_json_schema(),
            "strict": "true"
        }
    }

# Generate TOOLS from Pydantic models
