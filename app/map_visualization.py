"""Folium-based map helpers used by the Streamlit app."""
from __future__ import annotations

from typing import Iterable
from lib.data_types import Place

import folium
import html
from folium.plugins import HeatMap
import matplotlib
import matplotlib.colors as mcolors

_BASE_CIRCLE_RADIUS = 4

def _center(points: list[tuple[float, float]]) -> tuple[float, float]:
    return (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )


def _add_places(places: list[Place] | None, m: folium.Map) -> None:
    if not places:
        return
    for p in places:
        parts = [
            f"<b>{html.escape(str(p.name))}</b>",
            html.escape(str(p.amenity)),
        ]
        if p.rating is not None:
            parts.append(f"rating: {p.rating}")
        if p.opening_hours is not None:
            parts.append(p.opening_hours)
        if p.score is not None:
            parts.append(f"score: {p.score}")
        if p.price_level is not None:
            parts.append(f"price: {p.price_level}")
        folium.CircleMarker(
            location=(p.lat, p.lon),
            radius=_BASE_CIRCLE_RADIUS,
            popup=folium.Popup("<br>".join(parts), max_width=300),
            weight=1,
            color="#1f77b4",
            fill=True,
            fill_opacity=0.85
        ).add_to(m)


def places_map(places: Iterable[Place], zoom_start: int = 13, show_heatmap: bool = False) -> folium.Map:
    places = list(places)
    if not places:
        return folium.Map(location=(0, 0), zoom_start=2)

    center = _center([(p.lat, p.lon) for p in places])
    m = folium.Map(location=center, zoom_start=zoom_start)

    if show_heatmap:
        HeatMap(
            [(p.lat, p.lon) for p in places],
            radius=15,
            blur=10,
            max_zoom=15
        ).add_to(m)

    _add_places(places, m)
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


def opportunity_hex_map(
    cells: list[dict],
    places: list[Place] | None = None,
    zoom_start: int = 13,
    max_demand: float | None = None,
    min_demand: float | None = None,
    color_metric: str = "demand_score",  # "demand_score" | "competitor_density" | "opportunity_ratio"
    colormap: str = "RdYlGn_r",          # matplotlib colormap name; RdYlGn_r = green→yellow→red
    opacity_range: tuple[float, float] = (0.3, 0.65),
) -> folium.Map:
    """Отрисовать H3-сетку с градиентной заливкой.
    
    Args:
        cells: Список гексов из compute_opportunity_grid
        zoom_start: Начальный зум карты
        max_demand/min_demand: Границы нормализации (авто, если None)
        color_metric: Поле для расчёта цвета: 
            - "demand_score" → выше = "горячее" (зелёный→красный)
            - "competitor_density" → выше = насыщеннее рынок (синий→красный)
            - "opportunity_ratio" → demand / (competitor + 1) (универсальный)
        colormap: Название matplotlib colormap: 
            "YlOrRd", "RdYlGn", "Viridis", "Plasma", "coolwarm" и др.
        opacity_range: (min_opacity, max_opacity) для видимых ячеек
    """
    if not cells:
        return folium.Map(location=(0, 0), zoom_start=2)

    center = (cells[0]["center_lat"], cells[0]["center_lon"])
    m = folium.Map(location=center, zoom_start=zoom_start)

    # Вычисляем метрику для цвета
    values = []
    for c in cells:
        if color_metric == "opportunity_ratio":
            # Отношение спроса к конкуренции (чем выше — тем лучше)
            val = c["demand_score"] / (c["competitor_density"] + 1)
        else:
            val = c.get(color_metric, c["demand_score"])
        values.append(val)

    # Нормализация + настройка градиента
    visible_vals = [v for v, c in zip(values, cells) if c["is_visible"]]
    if not visible_vals:
        visible_vals = values
    min_val = min_demand if min_demand is not None else min(visible_vals)
    max_val = max_demand if max_demand is not None else max(visible_vals)
    span = max_val - min_val + 1e-6  # защита от деления на 0

    # Colormap из matplotlib (поддерживает 256 цветов)
    cmap = matplotlib.colormaps[colormap]
    norm = mcolors.Normalize(vmin=min_val, vmax=max_val)

    for c, val in zip(cells, values):
        # Прозрачные гексы (ниже порога спроса) — не рисуем заливку, только контур
        if not c["is_visible"]:
            folium.Polygon(
                locations=[list(pt) for pt in c["boundary"]],
                color="#888888",
                weight=1,
                fill=True,
                fill_opacity=0.1,  # почти прозрачный
                popup=f"Low demand<br>{color_metric}: {val:.2f}",
            ).add_to(m)
            continue

        # Видимые гексы — градиентная заливка
        normalized = (val - min_val) / span
        rgba = cmap(norm(val))  # [R, G, B, A]
        color = mcolors.to_hex(rgba[:3])
        opacity = opacity_range[0] + normalized * (opacity_range[1] - opacity_range[0])

        folium.Polygon(
            locations=[list(pt) for pt in c["boundary"]],
            color=color,
            weight=1.5,
            fill=True,
            fill_opacity=opacity,
            popup=(
                f"<b>{color_metric.replace('_', ' ').title()}</b>: {val:.2f}<br>"
                f"Demand: {c['demand_score']}<br>"
                f"Competition: {c['competitor_density']}<br>"
                f"Total POI: {c['total_places']}"
            ),
        ).add_to(m)
    
    _add_places(places, m)
    return m
