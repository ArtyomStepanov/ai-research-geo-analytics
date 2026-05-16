from pydantic import BaseModel

class Place(BaseModel):
    name: str
    amenity: str
    distance_km: float
    lat: float
    lon: float
