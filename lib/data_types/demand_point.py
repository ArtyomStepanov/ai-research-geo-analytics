from __future__ import annotations

from pydantic import BaseModel


class DemandPoint(BaseModel):
    lat: float
    lon: float
    count_people: float
    distance_km: float | None = None
