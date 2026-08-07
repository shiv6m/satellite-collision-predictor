"""
Turns a TLE into a trajectory: positions (km) over a time window.

SGP4 works in a frame called TEME (True Equator, Mean Equinox) and gives
back Earth-Centered-Inertial coordinates -- x, y, z in km, measured from
Earth's center, NOT from the ground. That's exactly what we want for
comparing two satellites' positions to each other, since we don't care
about lat/lon, just "how far apart are these two points in space."
"""
import numpy as np
from datetime import datetime, timedelta, timezone
from sgp4.api import Satrec, SatrecArray, jday


def _to_jd_fr(dt: datetime) -> tuple[float, float]:
    """Convert a datetime to SGP4's split julian date format (jd, fr)."""
    return jday(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second + dt.microsecond / 1e6)


def build_time_grid(start: datetime, duration_hours: float, step_seconds: float) -> list[datetime]:
    n_steps = int((duration_hours * 3600) // step_seconds) + 1
    return [start + timedelta(seconds=i * step_seconds) for i in range(n_steps)]


def propagate_satellite(line1: str, line2: str, times: list[datetime]) -> np.ndarray:
    """
    Propagate a single satellite across a list of times.
    Returns an (N, 3) array of ECI position vectors in km.
    Rows with propagation errors (e.g. decayed orbit) are NaN.
    """
    sat = Satrec.twoline2rv(line1, line2)
    jd = np.zeros(len(times))
    fr = np.zeros(len(times))
    for i, t in enumerate(times):
        jd[i], fr[i] = _to_jd_fr(t)

    error_codes, positions, _velocities = sat.sgp4_array(jd, fr)
    positions = np.array(positions)
    positions[error_codes != 0] = np.nan  # mark failed propagation steps
    return positions


def propagate_many(satellites: list[dict], times: list[datetime]) -> dict[int, np.ndarray]:
    """
    Propagate a batch of satellites (each dict has line1/line2/norad_id).
    Returns {norad_id: (N,3) position array}. Skips satellites whose TLE
    fails to parse (rare, but malformed/decayed entries do exist).
    """
    trajectories = {}
    for sat in satellites:
        try:
            trajectories[sat["norad_id"]] = propagate_satellite(sat["line1"], sat["line2"], times)
        except Exception:
            continue
    return trajectories
