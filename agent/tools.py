import os

from core_utils.coverage import find_underserved_areas
from core_utils.ranking import rank_by_distance, rank_by_score
from core_utils.search import nearest_places, search_by_name, search_places
from core_utils.filtering import filter_by_category, filter_by_rating
from core_utils.geo_utils import compute_distance, build_heatmap
from lib.data_types import Place
import ast

from typing import Any


def _tool_search_places(args: dict[str, Any]) -> list[Place]:
    near = None
    if "near_lat" in args and "near_lon" in args:
        near = (float(args["near_lat"]), float(args["near_lon"]))
    return search_places(
        category=ast.literal_eval(args.get("category")),
        near=near,
        max_distance_km=args.get("max_distance_km"),
        limit=int(args.get("limit", 10)),
    )


def _tool_nearest_places(args: dict[str, Any]) -> list[Place]:
    near = None
    if "near_lat" in args and "near_lon" in args:
        near = (float(args["near_lat"]), float(args["near_lon"]))
    return nearest_places(
        category=ast.literal_eval(args.get("category")),
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


def _tool_coverage(args: dict[str, Any]) -> list[dict]:
    return find_underserved_areas(
        category=args.get("category", "pharmacy"),
        top_k=int(args.get("top_k", 10)),
    )


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


def _coerce_points(raw: Any) -> list[tuple]:
    """LLM шлёт points по-разному: list[list], list[dict], JSON-строкой.

    Нормализуем в list[(lat, lon[, weight])]. НЕ используем ast.literal_eval
    вслепую (как в _tool_search_places) — он падает на None/'cafe'/'a,b'.
    """
    if raw is None:
        raise ValueError("heatmap: 'points' is required")
    if isinstance(raw, str):
        import json
        raw = json.loads(raw)          # JSON, не ast: предсказуемо падает с понятной ошибкой
    pts: list[tuple] = []
    for item in raw:
        if isinstance(item, dict):     # {"lat":.., "lon":.., "weight":..}
            lat, lon = item["lat"], item["lon"]
            w = item.get("weight")
            pts.append((lat, lon, w) if w is not None else (lat, lon))
        else:                          # [lat, lon] или [lat, lon, weight]
            pts.append(tuple(item))
    return pts


def _tool_heatmap(args: dict[str, Any]) -> dict:
    """Построить HeatMap и сохранить в HTML. Возвращает путь (JSON-сериализуемо).

    Карту (folium.Map) нельзя вернуть напрямую — agent.py делает json.dumps
    над результатом, а Map не сериализуется. Поэтому пишем файл и отдаём путь.
    """
    points = _coerce_points(args.get("points"))

    out_dir = args.get("out_dir", "outputs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, args.get("filename", "heatmap.html"))

    kwargs = {}
    for k in ("zoom_start", "radius", "legend", "legend_title"):
        if k in args:
            kwargs[k] = args[k]

    try:
        m = build_heatmap(points, **kwargs)
    except ValueError as e:
        return {"error": str(e)}      # пустой points и т.п. — понятная ошибка агенту

    m.save(out_path)
    return {"status": "ok", "path": out_path, "n_points": len(points)}
