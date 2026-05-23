from pydantic import BaseModel


class Hex(BaseModel):
    hex_id: str
    center_lat: float
    center_lon: float
    boundary: list[tuple[float, float]]
    row: int | None = None
    col: int | None = None
    demand_score: float
    competitor_density: float
    competitor_count: int
    competitor_avg_rating: float
    opportunity_score: float
    total_places: int
    is_visible: bool
