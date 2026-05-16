"""Folium-based map helpers used by the Streamlit app."""
from __future__ import annotations

from typing import Iterable
from lib.data_types import Place

import folium
from folium.plugins import HeatMap


def _center(points: list[tuple[float, float]]) -> tuple[float, float]:
    return (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )


def places_map(places: Iterable[Place], zoom_start: int = 13) -> folium.Map:
    places = list(places)
    if not places:
        return folium.Map(location=(0, 0), zoom_start=2)

    center = _center([(p.lat, p.lon) for p in places])
    m = folium.Map(location=center, zoom_start=zoom_start)
    for p in places:
        popup = f"<b>{p.name}</b><br>{p.amenity}"
        if "rating" in p:
            popup += f"<br>rating: {p.rating}"
        if "score" in p:
            popup += f"<br>score: {p.score}"
        folium.CircleMarker(
            location=(p.lat, p.lon),
            radius=5,
            popup=popup,
            color="#1f77b4",
            fill=True,
            fill_opacity=0.8,
        ).add_to(m)
    return m


def heatmap(points: Iterable[tuple[float, float]], zoom_start: int = 13) -> folium.Map:
    points = list(points)
    if not points:
        return folium.Map(location=(0, 0), zoom_start=2)
    m = folium.Map(location=_center(points), zoom_start=zoom_start)
    HeatMap(points).add_to(m)
    return m


def underserved_map(
    cells: list[dict],
    all_points: list[tuple[float, float]] | None = None,
    zoom_start: int = 13,
) -> folium.Map:
    """Show underserved cells as red squares; optionally overlay total-POI heatmap."""
    if not cells:
        return folium.Map(location=(0, 0), zoom_start=2)
    center = _center([(c["cell_lat"], c["cell_lon"]) for c in cells])
    m = folium.Map(location=center, zoom_start=zoom_start)
    if all_points:
        HeatMap(all_points, radius=10, blur=15).add_to(m)
    half = 0.003
    for c in cells:
        lat, lon = c["cell_lat"], c["cell_lon"]
        folium.Rectangle(
            bounds=[(lat - half, lon - half), (lat + half, lon + half)],
            color="#d62728",
            weight=2,
            fill=True,
            fill_opacity=0.35,
            popup=(
                f"underserved_score={c['underserved_score']}<br>"
                f"total={c['total_places']}"
            ),
        ).add_to(m)
    return m
