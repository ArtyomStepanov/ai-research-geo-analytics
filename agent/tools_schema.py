"""OpenAI-compatible tool schema definitions for the agent."""

from lib.data_types.agent_tools_schema import to_tool_schema
from lib.data_types.agent_tools_schema import (
    SearchPlacesRequest,
    RankPlacesRequest,
    UnderservedAreasRequest,
    FilterRequest,
    DistanceRequest
)

TOOLS = [
    to_tool_schema(
        SearchPlacesRequest,
        "search_places",
        "Search amenities (cafe, restaurant, pharmacy, bar, ...) from the local dataset. Optionally filter by distance from an anchor point."
    ),
    to_tool_schema(
        SearchPlacesRequest,
        "nearest_places",
        "Search N amenities (cafe, restaurant, pharmacy, bar, ...) near the point from the local dataset"
    ),
    to_tool_schema(
        SearchPlacesRequest,
        "search_by_name",
        "Search amenities (cafe, restaurant, pharmacy, bar, ...) from the local dataset by their name. Optionally filter by distance from an anchor point."
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
        "compute_distance",
        "Compute distance between two points. Returns number."
    ),
]
