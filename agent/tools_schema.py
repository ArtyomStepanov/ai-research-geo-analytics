"""OpenAI-compatible tool schema definitions for the agent."""

from lib.data_types.agent_tools_schema import to_tool_schema
from lib.data_types.agent_tools_schema import (
    SearchPlacesRequest,
    NearestPlacesRequest,
    SearchByNameRequest,
    RankPlacesRequest,
    FilterRequest,
    OpportunityGridRequest,
    DistanceRequest,
    HeatmapRequest,
    GeocodeRequest,
)

TOOLS = [
    to_tool_schema(
        GeocodeRequest,
        "geocode",
        "Convert a place name or landmark (toponym) to lat/lon coordinates. "
        "Call this FIRST when the user mentions a place name instead of numeric coordinates, "
        "then pass the returned lat/lon to search_places or nearest_places."
    ),
    to_tool_schema(
        SearchPlacesRequest,
        "search_places",
        "Search amenities (cafe, restaurant, pharmacy, bar, ...) from the local dataset."
        "Optionally filter by distance from an anchor point."
    ),
    to_tool_schema(
        NearestPlacesRequest,
        "nearest_places",
        "Search N amenities (cafe, restaurant, pharmacy, bar, ...) near the point from the local dataset"
    ),
    to_tool_schema(
        SearchByNameRequest,
        "search_by_name",
        "Search amenities (cafe, restaurant, pharmacy, bar, ...) from the local dataset by their name."
        "Optionally filter by distance from an anchor point."
    ),
    to_tool_schema(
        RankPlacesRequest,
        "rank_places",
        "Rank a previously returned list of places."
        "Strategy is either 'distance' (ascending distance_km) or 'score' (composite rating - distance)."
    ),
    to_tool_schema(
        OpportunityGridRequest,
        "opportunity_grid",
        "Compute a hex-grid opportunity map showing demand score, competitor density, and optimal "
        "locations for a new point of interest. Use for queries about: low/lacking coverage, "
        "underserved areas, where to open a new X, market saturation, best location analysis, "
        "'find areas with low X coverage', 'where do we lack X', 'open new X'."
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
    to_tool_schema(
        HeatmapRequest,
        "build_heatmap",
        "Render a heatmap of places already retrieved by search_places/nearest_places. "
        "Do NOT use for coverage or opportunity analysis — use opportunity_grid instead."
    ),
]
