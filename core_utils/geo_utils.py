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
    """Build a folium HeatMap from a list of (lat, lon) or (lat, lon, weight) points.

    TODO: расширить — радиус.
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
    
    weighted = [
        (p[0], p[1], p[2] if len(p) > 2 else 1.0)
        for p in points
    ]

    if kwargs.get("legend", True):
        title = kwargs.get("legend_title", "Интенсивность")
        low = kwargs.get("legend_low", "низкая")
        high = kwargs.get("legend_high", "высокая")
        legend_html = f"""
        <div style="
            position: fixed; bottom: 30px; left: 30px; z-index: 9999;
            background: white; padding: 10px 14px; border-radius: 6px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.3); font: 13px sans-serif;">
          <b>{title}</b><br>
          <div style="
              width: 160px; height: 12px; margin: 6px 0;
              background: linear-gradient(to right, blue, lime, yellow, red);">
          </div>
          <span style="float:left;">{low}</span>
          <span style="float:right;">{high}</span>
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

    HeatMap(weighted, radius=kwargs.get("radius", 12)).add_to(m)
    return m
