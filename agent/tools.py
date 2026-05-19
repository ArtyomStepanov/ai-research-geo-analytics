import os

from core_utils.coverage import compute_opportunity_grid
from core_utils.ranking import rank_by_distance, rank_by_score
from core_utils.search import nearest_places, search_by_name, search_places
from core_utils.filtering import filter_by_category, filter_by_rating
from core_utils.geo_utils import compute_distance, build_heatmap, _coerce_points
from lib.data_types import Place
import ast

from typing import Any


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
            'zoom_start': zoom_start
        }
    except Exception:
        pass  # Если запускается вне Streamlit (тесты), просто игнорируем

    # 2. Возвращаем агенту подтверждение (вместо пути к файлу)
    return {"status": "ok", "n_points": len(points)}


def _tool_opportunity_grid(args: dict[str, Any]) -> list[dict]:
    """Calculate hex-grid opportunity map and return structured cells."""
    
    cells = compute_opportunity_grid(
        category=args.get("category", "pharmacy"),
        hex_resolution=int(args.get("hex_resolution", 8)),
        demand_threshold=float(args.get("demand_threshold", 0.0)),
        competitor_rating_weight=float(args.get("competitor_rating_weight", 1.0)),
    )

    # Сохраняем в session_state, чтобы UI мог прочитать и отрисовать
    try:
        import streamlit as st
        st.session_state['opportunity_grid'] = {'cells': cells}
    except Exception:
        pass  # Игнорируем при запуске вне Streamlit (тесты/CLI)

    return cells
