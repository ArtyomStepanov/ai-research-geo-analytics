from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal, Tuple
import json

class Place(BaseModel):
    name: str
    amenity: str
    distance_km: float
    lat: float
    lon: float

class FilterRequest(BaseModel):
    places: List[Dict[str, Any]] = Field(..., description="List of places to filter")
    strategy: Literal["category", "rating"] = Field("rating", description="Filtering mode")
    category: str | None = Field(None, description="Required if strategy='category'")
    min_rating: float | None = Field(None, description="Required if strategy='rating'")

class DistanceRequest(BaseModel):
    p1: Tuple[float, float] = Field(
        ...,
        description="First point coords [lat, lon]"
    )
    p2: Tuple[float, float] = Field(
        ...,
        description="Second point coords [lat, lon]"
    )
# Pydantic автоматически сгенерирует валидную OpenAI-схему
schema = FilterRequest.model_json_schema()
# Адаптируем под формат OpenAI tools
filter_tool_schema = {
    "type": "function",
    "function": {
        "name": "filter_places",
        "description": "Filters places by category or rating.",
        "parameters": schema
    }
}

distance_tool_schema = {
    "type": "function",
    "function": {
        "name": "calculate_distance",
        "description": "Calc distance between 2 points. Returns number",
        "parameters": DistanceRequest.model_json_schema()
    }
}
print(json.dumps(distance_tool_schema, indent=4))