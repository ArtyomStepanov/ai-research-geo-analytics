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

_BASE_CIRCLE_RADIUS = 3


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


def _resolve_pinned_center(
    cells: list[Hex],
    pinned_hex_id: str | None,
) -> tuple[float, float] | None:
    """Вернуть координаты центра пин-гекса, если он задан.

    Сначала ищем гекс в `cells` (быстрее и точнее — берём посчитанный центр).
    Если гекса нет в сетке (например, пин пришёл из чата по гексу за пределами
    видимой области) — считаем центр напрямую через h3.

    Returns:
        (lat, lon) центра пин-гекса либо None, если pinned_hex_id не задан
        или невалиден.
    """
    if not pinned_hex_id:
        return None

    pinned_cell = next(
        (c for c in cells if c.hex_id == pinned_hex_id), None
    )
    if pinned_cell is not None:
        return (pinned_cell.center_lat, pinned_cell.center_lon)

    try:
        import h3
        lat, lon = h3.cell_to_latlng(pinned_hex_id)
        return (lat, lon)
    except Exception:
        return None


def opportunity_hex_map(
    cells: list[Hex],
    places: list[Place] | None = None,
    zoom_start: int = 13,
    color_metric: str = "opportunity_score",  # main B2B metric
    colormap: str = "RdYlGn",                 # red=bad, green=good
    demand_threshold: float = 50.0,
    low_demand_opacity: float = 0.10,
    colored_opacity: float = 0.55,
    highlighted_hex_ids: set[str] | None = None,
    pinned_hex_id: str | None = None,
    threshold: float | None = None,
    half_range: float | None = None,
) -> folium.Map:
    """Отрисовать H3-сетку с градиентной заливкой относительно порога.

    Цвет гекса определяется тем, насколько его метрика отличается от
    `threshold`: ровно на пороге — нейтрально-жёлтый, выше — зеленее,
    ниже — краснее. На отклонении >= `half_range` цвет полностью насыщен.

    Гексы с населением ниже `demand_threshold` отрисовываются почти
    прозрачным серым (логика «мало жителей -> карта здесь молчит»),
    независимо от значения метрики.

    Центрирование карты:
        - По умолчанию центр = среднее по видимым гексам.
        - Если задан `pinned_hex_id` — центр сдвигается на центр этого гекса,
          НО `zoom_start` остаётся прежним (не приближаем). Это даёт эффект
          «карта переехала на выбранный гекс», сохраняя общий масштаб обзора.

    Args:
        cells: Список гексов из compute_opportunity_grid.
        places: Конкуренты для отрисовки точками поверх гексов.
        zoom_start: Начальный зум карты. НЕ меняется при наличии пина —
            мы только сдвигаем центр.
        color_metric: Поле для расчёта цвета:
            - "opportunity_score" → главная B2B-метрика. По умолчанию.
            - "demand_score" → жители в гексе (для отладки).
            - "competitor_density" → насыщенность рынка (используй RdYlGn_r).
        colormap: Название matplotlib colormap.
            - "RdYlGn" для implant: высокий opportunity_score = зелёный.
            - "RdYlGn_r" для aggregate: высокий score конкурентов = красный.
        demand_threshold: Гексы с demand_score < этого значения становятся
            прозрачно-серыми (мало жителей -> не цветим).
        low_demand_opacity: Непрозрачность серой заливки малонаселённых гексов.
        colored_opacity: Непрозрачность цветных гексов. Одинакова для всех,
            чтобы насыщенность читалась чисто по цвету (а не по альфе).
        highlighted_hex_ids: Если задано, эти гексы выделяются обводкой,
            остальные становятся блёкло-серыми.
        pinned_hex_id: Если задан — карта центрируется на центре этого гекса
            (zoom не меняется), и сам гекс получает оранжевую обводку.
        threshold: Значение метрики, в котором гекс окрашен нейтрально.
            По умолчанию — среднее арифметическое по видимым достаточно
            населённым гексам.
        half_range: На сколько метрика должна отклониться от `threshold`,
            чтобы цвет насытился полностью. По умолчанию — 90-й перцентиль
            |value - threshold| среди тех же гексов.
    """
    if not cells:
        return folium.Map(location=(0, 0), zoom_start=2)

    # Центр карты по умолчанию — среднее по видимым гексам, чтобы не
    # перекосило одним выбросом за границей сетки.
    visible_cells = [c for c in cells if c.is_visible] or cells
    default_center = (
        sum(c.center_lat for c in visible_cells) / len(visible_cells),
        sum(c.center_lon for c in visible_cells) / len(visible_cells),
    )

    # Если задан пин — переезжаем на его центр. ZOOM НЕ ТРОГАЕМ: берём
    # тот же zoom_start, что был передан, чтобы общий масштаб обзора
    # сохранился. Так пользователь видит выбранный гекс + соседей в том
    # же приближении, что и всю сетку до выбора.
    pinned_center = _resolve_pinned_center(cells, pinned_hex_id)
    center = pinned_center if pinned_center is not None else default_center

    m = folium.Map(location=center, zoom_start=zoom_start)

    # Значения метрики для расчёта цвета (для всех гексов сразу)
    values = np.array(
        [getattr(c, color_metric, c.opportunity_score) for c in cells],
        dtype=np.float64,
    )
    demands = np.array([c.demand_score for c in cells], dtype=np.float64)
    visible_mask = np.array([c.is_visible for c in cells], dtype=bool)

    # Шкалу строим только по гексам, которые мы реально будем красить:
    # видимые И с достаточным спросом. Иначе среднее перекошено нулями
    # или малонаселёнными гексами и нейтральная точка уезжает.
    scaling_mask = visible_mask & (demands >= demand_threshold)
    scaling_vals = values[scaling_mask] if scaling_mask.any() else values[visible_mask]
    if scaling_vals.size == 0:
        scaling_vals = values  # совсем вырожденный случай

    # Точка нейтрали (жёлтый на RdYlGn): среднее арифметическое.
    if threshold is None:
        threshold = float(np.mean(scaling_vals))

    # Полудиапазон до полного насыщения цвета
    if half_range is None:
        half_range = float(np.percentile(np.abs(scaling_vals - threshold), 90))
    if half_range <= 0:
        half_range = 1.0  # все scores равны threshold → шкала вырождается в нейтраль

    cmap = matplotlib.colormaps[colormap]
    vmin = threshold - half_range
    vmax = threshold + half_range
    norm = mcolors.TwoSlopeNorm(vmin=vmin, vcenter=threshold, vmax=vmax)

    in_highlight_mode = bool(highlighted_hex_ids)

    for c, val in zip(cells, values):
        # 1) Невидимые гексы (контекст вокруг сетки): тонкий серый контур.
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

        # 2) Мало жителей -> прозрачно-серый, цвет метрики не показываем.
        # Это явное правило: на таких гексах оценка либо неустойчива, либо
        # бизнес-смысл слабый, и красить их цветом было бы вводящим в заблуждение.
        if c.demand_score < demand_threshold:
            folium.Polygon(
                locations=[list(pt) for pt in c.boundary],
                color="#999999",
                weight=1,
                fill=True,
                fill_color="#bbbbbb",
                fill_opacity=low_demand_opacity,
                popup=(
                    f"<b>Низкий спрос</b> ({c.demand_score:.0f} чел.)<br>"
                    f"Возможность: {c.opportunity_score:.2f}<br>"
                    f"Конкуренты: {c.competitor_count}<br>"
                    f"Всего мест: {c.total_places}"
                ),
            ).add_to(m)
            continue

        # 3) Цветной гекс: цвет = отклонение от threshold, прозрачность фиксирована.
        # TwoSlopeNorm не клипает за пределы [vmin, vmax] — клипаем вручную.
        val_clipped = float(np.clip(val, vmin, vmax))
        rgba = cmap(norm(val_clipped))
        color = mcolors.to_hex(rgba[:3])

        folium.Polygon(
            locations=[list(pt) for pt in c.boundary],
            color="#333333" if in_highlight_mode else color,
            weight=3.0 if in_highlight_mode else 1.5,
            fill=True,
            fill_color=color,
            fill_opacity=colored_opacity,
            popup=(
                f"<b>Возможность</b>: {c.opportunity_score:.2f}<br>"
                f"Спрос (жители): {c.demand_score}<br>"
                f"Конкуренты: {c.competitor_count} "
                f"(avg ⭐ {c.competitor_avg_rating:.1f})<br>"
                f"Всего мест: {c.total_places}"
            ),
        ).add_to(m)

    if pinned_hex_id:
        pinned_drawn = False
        for c in cells:
            if c.hex_id == pinned_hex_id:
                # Двойная отрисовка: сначала полупрозрачная оранжевая
                # заливка (чтобы пин был заметен на любом цветовом фоне),
                # сверху яркий контур.
                folium.Polygon(
                    locations=[list(pt) for pt in c.boundary],
                    color="#FF6B00",
                    weight=6,
                    fill=True,
                    fill_color="#FF6B00",
                    fill_opacity=0.35,
                    popup=f"<b>📍 {c.hex_id}</b>",
                ).add_to(m)
                # Внешний контур поверх — на случай если границы сливаются
                # с уже отрисованным цветным гексом.
                folium.Polygon(
                    locations=[list(pt) for pt in c.boundary],
                    color="#FFFFFF",
                    weight=2,
                    fill=False,
                    opacity=1.0,
                ).add_to(m)
                pinned_drawn = True
                break
        # Если гекс отсутствует в сетке — отрисуем по геометрии из его
        # координат через h3. Полезно, если пин пришёл из чата по гексу,
        # которого нет в текущей видимой сетке.
        if not pinned_drawn:
            try:
                import h3
                boundary = h3.cell_to_boundary(pinned_hex_id)
                folium.Polygon(
                    locations=[list(pt) for pt in boundary],
                    color="#FF6B00",
                    weight=6,
                    fill=True,
                    fill_color="#FF6B00",
                    fill_opacity=0.35,
                    popup=f"<b>📍 {pinned_hex_id}</b> (вне сетки)",
                ).add_to(m)
            except Exception:
                pass

    _add_places(places, m)
    return m
