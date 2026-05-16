from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal, Tuple
import json

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

def generate_tool_schemas(tool, name, description) -> List[Dict[str, Any]]:
    schema = {
        "type": "function",
        "function": {
            "name": f"{name}",
            "description": f"{description}",
            "parameters": tool.model_json_schema()
        }
    }
    return json.dumps(schema, indent=4)

