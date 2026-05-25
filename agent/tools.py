from __future__ import annotations

from typing import Any

import h3

from core_utils.coverage import compute_opportunity_grid
from core_utils.filtering import filter_by_category, filter_by_rating
from core_utils.geo_utils import compute_distance, _coerce_points, geocode
from core_utils.ranking import rank_by_distance, rank_by_score
from core_utils.search import nearest_places, search_by_name, search_places
from lib.data_types import Place, Hex


def _tool_search_places(args: dict[str, Any]) -> list[Place]:
    near = None
    if "near_lat" in args and "near_lon" in args:
        near = (float(args["near_lat"]), float(args["near_lon"]))
    cat = args.get("category")
    if isinstance(cat, str):
        cat = [cat]
    return search_places(
        category=cat,
        near=near,
        max_distance_km=args.get("max_distance_km"),
        limit=int(args.get("limit", 10)),
    )


def _tool_nearest_places(args: dict[str, Any]) -> list[Place]:
    near = None
    if "near_lat" in args and "near_lon" in args:
        near = (float(args["near_lat"]), float(args["near_lon"]))
    cat = args.get("category")
    if isinstance(cat, str):
        cat = [cat]
    return nearest_places(
        category=cat,
        point=near,
        limit=int(args.get("limit", 10)),
    )


def _tool_search_by_name(args: dict[str, Any]) -> list[Place]:
    near = None
    if "near_lat" in args and "near_lon" in args:
        near = (float(args["near_lat"]), float(args["near_lon"]))
    return search_by_name(name=args["name"], point=near)


def _tool_rank(args: dict[str, Any]) -> list[Place]:
    places = args.get("places") or []
    strategy = args.get("strategy", "score")

    if places and isinstance(places[0], dict):
        places = [Place(**p) for p in places]

    if strategy == "distance":
        return rank_by_distance(places)
    return rank_by_score(places)


def _tool_filtering(args: dict[str, Any]) -> list[Place]:
    places = args.get("places") or []
    strategy = args.get("strategy", "rating")

    if places and isinstance(places[0], dict):
        places = [Place(**p) for p in places]

    if strategy == "category":
        category = args.get("category")
        return filter_by_category(places, category)
    min_rating = args.get("min_rating", 0)
    return filter_by_rating(places, min_rating)


def _tool_distance(args: dict[str, Any]) -> float:
    p1, p2 = args.get("p1"), args.get("p2")
    return compute_distance(p1, p2)


def _tool_build_heatmap(args: dict[str, Any]) -> dict:
    """Построить HeatMap и передать данные в UI (без сохранения файлов)."""
    # Нормализуем точки (список кортежей)
    try:
        points = _coerce_points(args.get("points"))
    except ValueError as e:
        return {"error": str(e)}
    radius = args.get("radius", 15)
    zoom_start = args.get("zoom_start", 13)
    # 1. Сохраняем данные в Session State, чтобы UI мог их прочитать
    try:
        import streamlit as st
        # Мы используем уникальный ключ, чтобы не конфликтовать с другими данными
        st.session_state['agent_heatmap'] = {
            'points': points,
            'radius': radius,
            'zoom_start': zoom_start,
            'args': dict(args),  # копия для sidebar
        }
    except Exception:
        pass  # Если запускается вне Streamlit (тесты), просто игнорируем
    # 2. Возвращаем агенту подтверждение (вместо пути к файлу)
    return {"status": "ok", "n_points": len(points)}


def _tool_geocode(args: dict[str, Any]) -> dict:
    location = args.get("location", "").strip()
    city_hint = args.get("city_hint", "")
    if not location:
        return {"error": "location is required"}
    result = geocode(location, city_hint)
    if result is None:
        return {"error": f"Could not geocode '{location}'"}
    lat, lon = result
    return {"lat": lat, "lon": lon, "location": location}


# row = origin_i - i  (row>0 = East, row<0 = West)
# col = j - origin_j  (col<0 = North, col>0 = South)
# For H3 ring-1, the 6 (dr, dc) offsets map to these compass labels.
_IJ_TO_DIRECTION: dict[tuple[int, int], str] = {
    ( 0, -1): "С",
    (+1,  0): "В",
    (+1, +1): "ЮВ",
    ( 0, +1): "Ю",
    (-1,  0): "З",
    (-1, -1): "СЗ",
}


def _tool_nearest_hexes(args: dict[str, Any]) -> dict:
    """Return a hex and its ring-neighbours with compass direction labels."""
    hex_id = args.get("hex_id", "").strip()
    radius = int(args.get("radius", 1))

    try:
        import streamlit as st
        opp = st.session_state.get("opportunity_grid")
    except Exception:
        opp = None

    if not opp or not opp.get("cells"):
        return {"error": "Opportunity grid not loaded. Run opportunity_grid first."}
    if not hex_id:
        return {"error": "hex_id is required."}

    cells_by_id = {c.hex_id: c for c in opp["cells"]}

    def _slim(c: Hex) -> dict:
        return c.model_dump(exclude={"boundary"})

    target_cell = cells_by_id.get(hex_id)

    target_dict = None
    if target_cell is not None:
        target_dict = _slim(target_cell)
        target_dict["label"] = "Ц"

    neighbors: list[Hex] = []
    for h in h3.grid_disk(hex_id, radius):
        if h not in cells_by_id or h == hex_id:
            continue
        neighbor_cell = cells_by_id[h]
        label = None
        if radius == 1 and target_cell is not None:
            dr = neighbor_cell.row - target_cell.row
            dc = neighbor_cell.col - target_cell.col
            label = _IJ_TO_DIRECTION.get((dr, dc), "?")
        slim = _slim(neighbor_cell)
        slim["label"] = label
        neighbors.append(slim)

    try:
        import streamlit as st
        st.session_state["highlighted_hexes"] = {hex_id} | {n["hex_id"] for n in neighbors}
    except Exception:
        pass

    return {
        "target_hex": hex_id,
        "target_in_grid": target_cell is not None,
        "target_cell": target_dict,
        "radius": radius,
        "neighbors": neighbors,
    }


def _tool_opportunity_grid(args: dict[str, Any]) -> list[Hex]:
    """Calculate hex-grid opportunity map and return structured cells."""

    cells = compute_opportunity_grid(
        category=args.get("category", "pharmacy"),
        hex_resolution=int(args.get("hex_resolution", 8)),
        visibility_threshold=float(args.get("demand_threshold", 0.0)),
        strategy=args.get("strategy", "implant"),
    )
    try:
        import streamlit as st
        from .db import save_opportunity_grid
        chat_id = st.session_state.get('chat_id')
        grid_data = {'cells': cells, 'args': dict(args)}
        st.session_state['opportunity_grid'] = grid_data
        if chat_id:
            save_opportunity_grid(chat_id, {'cells': [c.model_dump() for c in cells], 'args': dict(args)})
    except Exception:
        pass  # Игнорируем при запуске вне Streamlit (тесты/CLI)

    return cells
