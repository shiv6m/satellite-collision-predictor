"""
Two-stage conjunction screening.

Stage 1 (coarse filter): checking every satellite pair with full
propagation is O(n^2) and expensive -- 500 satellites is already ~125,000
pairs. So first we throw out any pair whose orbits can't possibly cross:
if satellite A never gets higher than 400km and satellite B never gets
lower than 800km, they can never be close, no matter where they are in
their orbits. This is done from the TLE alone (no propagation needed) by
computing each orbit's perigee/apogee (closest/farthest point from Earth).

Stage 2 (fine screening): for the much smaller set of pairs that survive
stage 1, we actually propagate both satellites across the time window and
measure the real 3D distance between them at each timestep.
"""
import numpy as np
from datetime import datetime
from sgp4.api import Satrec, jday
from .propagate import _to_jd_fr

EARTH_RADIUS_KM = 6378.135


def altitude_band(line1: str, line2: str) -> tuple[float, float]:
    """Returns (perigee_altitude_km, apogee_altitude_km) from a TLE, no propagation needed."""
    sat = Satrec.twoline2rv(line1, line2)
    perigee_km = sat.a * (1 - sat.ecco) * EARTH_RADIUS_KM
    apogee_km = sat.a * (1 + sat.ecco) * EARTH_RADIUS_KM
    return perigee_km - EARTH_RADIUS_KM, apogee_km - EARTH_RADIUS_KM


def find_candidate_pairs(satellites: list[dict], margin_km: float = 50.0) -> list[tuple[dict, dict]]:
    """Stage 1: keep only pairs whose altitude bands overlap (+ margin)."""
    bands = []
    for sat in satellites:
        try:
            lo, hi = altitude_band(sat["line1"], sat["line2"])
            bands.append((sat, lo - margin_km, hi + margin_km))
        except Exception:
            continue  # bad TLE, skip

    candidates = []
    for i in range(len(bands)):
        sat_a, lo_a, hi_a = bands[i]
        for j in range(i + 1, len(bands)):
            sat_b, lo_b, hi_b = bands[j]
            if lo_a <= hi_b and lo_b <= hi_a:  # ranges overlap
                candidates.append((sat_a, sat_b))
    return candidates


def _propagate_with_velocity(line1: str, line2: str, times: list[datetime]):
    sat = Satrec.twoline2rv(line1, line2)
    jd = np.zeros(len(times))
    fr = np.zeros(len(times))
    for i, t in enumerate(times):
        jd[i], fr[i] = _to_jd_fr(t)
    error_codes, positions, velocities = sat.sgp4_array(jd, fr)
    positions, velocities = np.array(positions), np.array(velocities)
    positions[error_codes != 0] = np.nan
    velocities[error_codes != 0] = np.nan
    return positions, velocities


def screen_pair(sat_a: dict, sat_b: dict, times: list[datetime]):
    """
    Stage 2: propagate both satellites and find their closest approach.
    Returns dict with miss_distance_km, time_of_closest_approach,
    relative_speed_km_s -- or None if propagation fails for either.
    """
    try:
        pos_a, vel_a = _propagate_with_velocity(sat_a["line1"], sat_a["line2"], times)
        pos_b, vel_b = _propagate_with_velocity(sat_b["line1"], sat_b["line2"], times)
    except Exception:
        return None

    diff = pos_a - pos_b
    distances = np.linalg.norm(diff, axis=1)  # km at each timestep

    if np.all(np.isnan(distances)):
        return None

    min_idx = int(np.nanargmin(distances))
    rel_speed = float(np.linalg.norm(vel_a[min_idx] - vel_b[min_idx]))

    return {
        "miss_distance_km": float(distances[min_idx]),
        "time_of_closest_approach": times[min_idx],
        "relative_speed_km_s": rel_speed,
    }
