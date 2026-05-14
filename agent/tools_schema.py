"""OpenAI-compatible tool schema definitions for the agent."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_places",
            "description": (
                "Search amenities (cafe, restaurant, pharmacy, bar, ...) "
                "from the local dataset. Optionally filter by distance from an anchor point."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "OSM amenity tag, e.g. 'cafe'"},
                    "near_lat": {"type": "number"},
                    "near_lon": {"type": "number"},
                    "max_distance_km": {"type": "number"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rank_places",
            "description": (
                "Rank a previously returned list of places. Strategy is either "
                "'distance' (ascending distance_km) or 'score' (composite rating - distance)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "places": {"type": "array", "items": {"type": "object"}},
                    "strategy": {"type": "string", "enum": ["distance", "score"]},
                },
                "required": ["places", "strategy"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_underserved_areas",
            "description": (
                "Find grid cells in the city where a given amenity category is "
                "underrepresented relative to overall POI density. Use for 'where is X missing' queries."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "e.g. 'pharmacy'"},
                    "top_k": {"type": "integer", "default": 10},
                },
                "required": ["category"],
            },
        },
    },
]
