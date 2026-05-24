"""Folium-based map helpers used by the Streamlit app."""
from __future__ import annotations

import html
from typing import Iterable

import folium
import matplotlib
import matplotlib.colors as mcolors
import numpy as np
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
            parts.append(f"рейтинг: {p.rating}")
        if p.score is not None:
            parts.append(f"скор: {p.score}")
        if p.avg_bill is not None:
            parts.append(f"цена: {p.avg_bill}₽")
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
    max_demand: float | None = None,        # deprecated: см. half_range
    min_demand: float | None = None,        # deprecated: см. half_range
    color_metric: str = "opportunity_score",  # main B2B metric
    colormap: str = "RdYlGn",                 # red=bad, green=good
    opacity_range: tuple[float, float] = (0.3, 0.65),
    highlighted_hex_ids: set[str] | None = None,
    pinned_hex_id: str | None = None,
    threshold: float | None = None,
    half_range: float | None = None,
) -> folium.Map:
    """Отрисовать H3-сетку с градиентной заливкой относительно порога.

    Цвет гекса определяется тем, насколько его метрика отличается от
    `threshold`: ровно на пороге — нейтрально-жёлтый, выше — зеленее,
    ниже — краснее. На отклонении >= `half_range` цвет полностью насыщен.

    Args:
        cells: Список гексов из compute_opportunity_grid.
        places: Конкуренты для отрисовки точками поверх гексов.
        zoom_start: Начальный зум карты.
        color_metric: Поле для расчёта цвета:
            - "opportunity_score" → главная B2B-метрика. По умолчанию.
            - "demand_score" → POI кроме конкурентов (прокси трафика).
            - "competitor_density" → насыщенность рынка (используй RdYlGn_r).
        colormap: Название matplotlib colormap.
            Для opportunity_score — "RdYlGn" (красный→жёлтый→зелёный).
            Для competitor_density — "RdYlGn_r".
        opacity_range: (min_opacity, max_opacity). Прозрачность определяется
            `demand_score` (не opportunity): нет жителей → прозрачнее.
        highlighted_hex_ids: Если задано, эти гексы выделяются обводкой,
            остальные становятся блёкло-серыми.
        threshold: Значение метрики, в котором гекс окрашен нейтрально.
            По умолчанию — медиана видимых гексов (тогда покраска просто
            показывает «лучше/хуже типичного», без абсолютного смысла).
            Передавай явно для бизнес-порога (например, средний scoreR
            существующих заведений категории).
        half_range: На сколько метрика должна отклониться от `threshold`,
            чтобы цвет насытился полностью. По умолчанию — 90-й перцентиль
            |value - threshold| среди видимых гексов.
        max_demand / min_demand: deprecated. Если заданы оба и `half_range`
            не указан, используются для вычисления симметричного полудиапазона
            вокруг threshold.
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
    values = np.array(
        [getattr(c, color_metric, c.opportunity_score) for c in cells],
        dtype=np.float64,
    )

    # Видимые гексы определяют шкалу — пустые «контекстные» не должны её сжимать
    visible_mask = np.array([c.is_visible for c in cells], dtype=bool)
    visible_vals = values[visible_mask] if visible_mask.any() else values

    # Точка нейтрали (жёлтый на RdYlGn). Если не задана — медиана видимых.
    if threshold is None:
        threshold = float(np.median(visible_vals))

    # Полудиапазон до полного насыщения цвета
    if half_range is None:
        if min_demand is not None and max_demand is not None:
            # Обратная совместимость со старыми вызовами
            half_range = max(threshold - min_demand, max_demand - threshold)
        else:
            half_range = float(np.percentile(np.abs(visible_vals - threshold), 90))
    if half_range <= 0:
        half_range = 1.0  # все scores равны threshold → шкала вырождается в нейтраль

    cmap = matplotlib.colormaps[colormap]
    vmin = threshold - half_range
    vmax = threshold + half_range
    norm = mcolors.TwoSlopeNorm(vmin=vmin, vcenter=threshold, vmax=vmax)

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
                    f"<b>Пусто / низкая активность</b><br>"
                    f"Всего мест: {c.total_places}<br>"
                    f"Возможность: {c.opportunity_score:.2f}"
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
                    f"<b>Возможность</b>: {c.opportunity_score:.2f}<br>"
                    f"Спрос: {c.demand_score}<br>"
                    f"Конкуренты: {c.competitor_count}<br>"
                    f"Всего мест: {c.total_places}"
                ),
            ).add_to(m)
            continue

        # Видимые гексы: цвет = отклонение от threshold, прозрачность = спрос.
        # TwoSlopeNorm не клипает за пределы [vmin, vmax] — клипаем вручную.
        val_clipped = float(np.clip(val, vmin, vmax))
        rgba = cmap(norm(val_clipped))
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
                f"<b>Возможность</b>: {c.opportunity_score:.2f}<br>"
                f"Спрос (др. места): {c.demand_score}<br>"
                f"Конкуренты: {c.competitor_count} "
                f"(avg ⭐ {c.competitor_avg_rating:.1f})<br>"
                f"Всего мест: {c.total_places}"
            ),
        ).add_to(m)

    if pinned_hex_id:
        for c in cells:
            if c.hex_id == pinned_hex_id:
                folium.Polygon(
                    locations=[list(pt) for pt in c.boundary],
                    color="#FF6B00",
                    weight=5,
                    fill=False,
                    popup=f"<b>📍 {c.hex_id}</b>",
                ).add_to(m)
                break

    _add_places(places, m)
    return m
