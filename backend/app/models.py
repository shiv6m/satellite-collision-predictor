"""Data models shared across the backend."""
from datetime import datetime
from pydantic import BaseModel


class Satellite(BaseModel):
    norad_id: int
    name: str
    line1: str  # TLE line 1
    line2: str  # TLE line 2


class ConjunctionEvent(BaseModel):
    sat1_norad_id: int
    sat1_name: str
    sat2_norad_id: int
    sat2_name: str
    time_of_closest_approach: datetime
    miss_distance_km: float
    relative_speed_km_s: float
    risk_level: str  # "low" | "moderate" | "high"
