"""Geospatial helpers: distances, heatmaps, simple aggregations."""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometers."""
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def compute_distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """Alias of haversine_km, for readability in tools/agent."""
    return haversine_km(p1[0], p1[1], p2[0], p2[1])


def build_heatmap(points, **kwargs):  # noqa: ANN001 - returns folium.Map
    """Build a folium HeatMap from a list of (lat, lon) points.

    TODO: расширить — веса, радиус, легенда.
    """
    import folium
    from folium.plugins import HeatMap

    if not points:
        raise ValueError("No points to plot")
    center = (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )
    m = folium.Map(location=center, zoom_start=kwargs.get("zoom_start", 13))
    HeatMap(points, radius=kwargs.get("radius", 12)).add_to(m)
    return m
