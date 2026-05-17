"""Geospatial helpers: distances, heatmaps, simple aggregations."""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

import shapely
import numpy as np
import osmnx as ox
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point

ox.settings.use_cache = True

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometers."""
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def haversine_km_array(lat0: float, lon0: float, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Vectorized great-circle distance from one anchor (lat0, lon0)
    to arrays of points. Mirrors haversine_km but operates on numpy arrays.
    """
    r = 6371.0
    lat0, lon0 = np.radians(lat0), np.radians(lon0)
    lat, lon = np.radians(lat), np.radians(lon)
    dlat = lat - lat0
    dlon = lon - lon0
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat0) * np.cos(lat) * np.sin(dlon / 2.0) ** 2
    return 2.0 * r * np.arcsin(np.sqrt(a))


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

    # TODO: debug
    if kwargs.get("legend", False):
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


DEFAULT_SPEEDS = {"walk": 4.75, "drive": 40, "bike": 10} # TODO: уточнить

def isochrone(point: tuple[float, float],
              minutes: float = 30.0,
              mode: str = "walk"
) -> "shapely.Polygon":
    """Зона доступности из point за minutes на режиме mode ('walk'|'drive'|'bike')."""
    speed = DEFAULT_SPEEDS[mode]
    # 1. запас по dist: путь за minutes на этой скорости + 30% буфер
    dist_m = (speed * 1000 / 60) * minutes * 1.3
    G = ox.graph_from_point(point, dist=dist_m, network_type=mode, simplify=True)

    # 2. привязка точки к узлу — X=lon, Y=lat (ловушка!)
    center = ox.nearest_nodes(G, X=point[1], Y=point[0])

    # 3. вес-время в минутах (единицы согласованы с radius ниже)
    mpm = speed * 1000 / 60
    for u, v, k, data in G.edges(keys=True, data=True):
        data["time"] = data["length"] / mpm

    # 4. подграф достижимости
    sub = nx.ego_graph(G, center, radius=minutes, distance="time")
    if sub.number_of_nodes() < 3:
        raise ValueError("Недостаточно узлов для полигона — проверь dist/minutes")

    # 5. узлы -> полигон (convex_hull: baseline, завышает зону)
    pts = [Point(d["x"], d["y"]) for _, d in sub.nodes(data=True)]
    return gpd.GeoSeries(pts).union_all().convex_hull
