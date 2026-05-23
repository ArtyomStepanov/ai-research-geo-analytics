"""Folium-based map helpers used by the Streamlit app."""
from __future__ import annotations

import html
from typing import Iterable

import folium
import matplotlib
import matplotlib.colors as mcolors
from folium.plugins import HeatMap

from lib.data_types import Place, Hex

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
        if p.score is not None:
            parts.append(f"score: {p.score}")
        if p.price_level is not None:
            parts.append(f"price: {p.price_level}₽")
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
    cells: list[Hex],
    places: list[Place] | None = None,
    zoom_start: int = 13,
    max_demand: float | None = None,
    min_demand: float | None = None,
    color_metric: str = "opportunity_score",  # main B2B metric
    colormap: str = "RdYlGn",                 # red=bad, green=good
    opacity_range: tuple[float, float] = (0.3, 0.65),
    highlighted_hex_ids: set[str] | None = None,
) -> folium.Map:
    """Отрисовать H3-сетку с градиентной заливкой.

    Args:
        cells: Список гексов из compute_opportunity_grid.
        places: Конкуренты для отрисовки точками поверх гексов.
        zoom_start: Начальный зум карты.
        max_demand/min_demand: Границы нормализации (авто, если None).
        color_metric: Поле для расчёта цвета:
            - "opportunity_score" → главная B2B-метрика (demand - competition).
              Высокая = хорошее место под новую точку. По умолчанию.
            - "demand_score" → POI кроме конкурентов (прокси трафика).
            - "competitor_density" → насыщенность рынка.
        colormap: Название matplotlib colormap.
            Для opportunity_score используй "RdYlGn" (красный→зелёный).
            Для competitor_density — "RdYlGn_r" (зелёный→красный, т.к. высокая
            конкуренция = плохо).
        opacity_range: (min_opacity, max_opacity) для видимых ячеек.
    """
    if not cells:
        return folium.Map(location=(0, 0), zoom_start=2)

    # Центр карты — медиана по видимым гексам, чтобы не перекосило одним выбросом
    visible_cells = [c for c in cells if c.is_visible] or cells
    center = (
        sum(c.center_lat for c in visible_cells) / len(visible_cells),
        sum(c.center_lon for c in visible_cells) / len(visible_cells),
    )
    m = folium.Map(location=center, zoom_start=zoom_start)

    # Значения метрики для расчёта цвета
    values = [getattr(c, color_metric, c.opportunity_score) for c in cells]

    # Нормализация по ВИДИМЫМ ячейкам, чтобы выбросы из «контекстных»
    # пустых гексов не сжимали шкалу
    visible_vals = [v for v, c in zip(values, cells) if c.is_visible]
    if not visible_vals:
        visible_vals = values
    min_val = min_demand if min_demand is not None else min(visible_vals)
    max_val = max_demand if max_demand is not None else max(visible_vals)
    span = max_val - min_val + 1e-6

    cmap = matplotlib.colormaps[colormap]
    norm = mcolors.Normalize(vmin=min_val, vmax=max_val)

    # Прозрачность определяется спросом (demand_score), а не opportunity.
    # Нет спроса → прозрачный; много жителей → насыщенный цвет.
    demand_vals = [c.demand_score for c in cells if c.is_visible]
    d_min = min(demand_vals) if demand_vals else 0.0
    d_max = max(demand_vals) if demand_vals else 1.0
    d_span = d_max - d_min + 1e-6

    in_highlight_mode = bool(highlighted_hex_ids)

    for c, val in zip(cells, values):
        # Невидимые гексы (контекст вокруг): тонкий серый контур
        if not c.is_visible:
            folium.Polygon(
                locations=[list(pt) for pt in c.boundary],
                color="#888888",
                weight=1,
                fill=True,
                fill_opacity=0.08,
                popup=(
                    f"<b>Empty / low activity</b><br>"
                    f"Total POI: {c.total_places}<br>"
                    f"Opportunity: {c.opportunity_score:.2f}"
                ),
            ).add_to(m)
            continue

        is_highlighted = (not in_highlight_mode) or (c.hex_id in highlighted_hex_ids)

        if not is_highlighted:
            folium.Polygon(
                locations=[list(pt) for pt in c.boundary],
                color="#aaaaaa",
                weight=1,
                fill=True,
                fill_color="#cccccc",
                fill_opacity=0.10,
                popup=(
                    f"<b>Opportunity</b>: {c.opportunity_score:.2f}<br>"
                    f"Demand: {c.demand_score}<br>"
                    f"Competitors: {c.competitor_count}<br>"
                    f"Total POI: {c.total_places}"
                ),
            ).add_to(m)
            continue

        # Видимые гексы: цвет = конкуренция, прозрачность = спрос
        rgba = cmap(norm(val))
        color = mcolors.to_hex(rgba[:3])
        demand_norm = (c.demand_score - d_min) / d_span
        opacity = opacity_range[0] + demand_norm * (opacity_range[1] - opacity_range[0])

        folium.Polygon(
            locations=[list(pt) for pt in c.boundary],
            color="#333333" if in_highlight_mode else color,
            weight=3.0 if in_highlight_mode else 1.5,
            fill=True,
            fill_color=color,
            fill_opacity=opacity,
            popup=(
                f"<b>Opportunity</b>: {c.opportunity_score:.2f}<br>"
                f"Demand (other POI): {c.demand_score}<br>"
                f"Competitors: {c.competitor_count} "
                f"(avg ⭐ {c.competitor_avg_rating:.1f})<br>"
                f"Total POI: {c.total_places}"
            ),
        ).add_to(m)

    _add_places(places, m)
    return m
