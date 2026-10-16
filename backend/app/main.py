"""
FastAPI backend for the satellite collision predictor.

Flow on startup:
  1. Background task fetches TLEs from CelesTrak every REFRESH_INTERVAL_SECONDS.
  2. Runs two-stage conjunction screening across the tracked group.
  3. Caches the results in memory and pushes them to any connected
     WebSocket clients -- this is the "real-time" part: the dashboard
     doesn't poll, the server pushes when new data lands.

For a resume-grade version, swap the in-memory cache for Supabase (you
already know it): insert each ConjunctionEvent into a table, which gives
you history, and lets multiple backend instances share state. The REST
endpoints below would then read from Supabase instead of the local dict.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .propagate import build_time_grid, propagate_satellite
from .risk import classify, is_reportable
from .screening import find_candidate_pairs, screen_pair
from .tle_fetch import fetch_tle_group

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("collision-predictor")

TRACKED_GROUP = "stations"  # start small (~15 sats) while you're testing;
# bump to "starlink" (~6000) once it's working
REFRESH_INTERVAL_SECONDS = 300  # how often to re-fetch TLEs + re-screen
SCREEN_WINDOW_HOURS = 24  # how far ahead to look for conjunctions
SCREEN_STEP_SECONDS = 30  # time resolution of the screening pass

state: dict[str, Any] = {
    "satellites": [],  # last fetched TLE set
    "conjunctions": [],  # last screening results (list of dicts)
    "last_updated": None,
}
connected_clients: set[WebSocket] = set()


async def refresh_loop() -> None:
    while True:
        try:
            await run_screening_pass()
        except Exception:
            log.exception("Screening pass failed, will retry next interval")
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)


async def run_screening_pass() -> None:
    log.info(f"Fetching TLE group '{TRACKED_GROUP}'...")
    satellites = await fetch_tle_group(TRACKED_GROUP)
    log.info(f"Fetched {len(satellites)} satellites")

    times = build_time_grid(datetime.now(UTC), SCREEN_WINDOW_HOURS, SCREEN_STEP_SECONDS)

    candidates = find_candidate_pairs(satellites)
    log.info(f"{len(candidates)} candidate pairs after coarse filter")

    events: list[dict[str, Any]] = []
    for sat_a, sat_b in candidates:
        result = screen_pair(sat_a, sat_b, times)
        if result and is_reportable(result["miss_distance_km"]):
            events.append(
                {
                    "sat1_norad_id": sat_a["norad_id"],
                    "sat1_name": sat_a["name"],
                    "sat2_norad_id": sat_b["norad_id"],
                    "sat2_name": sat_b["name"],
                    "time_of_closest_approach": result["time_of_closest_approach"].isoformat(),
                    "miss_distance_km": round(result["miss_distance_km"], 3),
                    "relative_speed_km_s": round(result["relative_speed_km_s"], 3),
                    "risk_level": classify(
                        result["miss_distance_km"], result["relative_speed_km_s"]
                    ),
                }
            )

    events.sort(key=lambda e: e["miss_distance_km"])
    state["satellites"] = satellites
    state["conjunctions"] = events
    state["last_updated"] = datetime.now(UTC).isoformat()
    log.info(f"Found {len(events)} reportable conjunctions")

    await broadcast(
        {
            "type": "conjunctions_update",
            "data": events,
            "last_updated": state["last_updated"],
        }
    )


async def broadcast(message: dict[str, Any]) -> None:
    dead: set[WebSocket] = set()
    for ws in connected_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.add(ws)
    connected_clients.difference_update(dead)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(refresh_loop())
    yield
    task.cancel()


app = FastAPI(title="Satellite Collision Predictor", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to your frontend's origin before deploying
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "last_updated": state["last_updated"]}


@app.get("/satellites")
def get_satellites() -> dict[str, Any]:
    return {"count": len(state["satellites"]), "satellites": state["satellites"]}


@app.get("/conjunctions")
def get_conjunctions() -> dict[str, Any]:
    return {
        "count": len(state["conjunctions"]),
        "last_updated": state["last_updated"],
        "conjunctions": state["conjunctions"],
    }


@app.post("/refresh")
async def manual_refresh() -> dict[str, Any]:
    """Trigger an immediate screening pass instead of waiting for the interval."""
    await run_screening_pass()
    return {"status": "refreshed", "count": len(state["conjunctions"])}


@app.websocket("/ws/conjunctions")
async def ws_conjunctions(websocket: WebSocket) -> None:
    await websocket.accept()
    connected_clients.add(websocket)
    # send current state immediately so the client doesn't wait for the next cycle
    await websocket.send_json(
        {
            "type": "conjunctions_update",
            "data": state["conjunctions"],
            "last_updated": state["last_updated"],
        }
    )
    try:
        while True:
            await websocket.receive_text()  # keep connection alive; ignore client msgs
    except WebSocketDisconnect:
        connected_clients.discard(websocket)


# ---------------------------------------------------------------------------
# Frontend support: on-demand position queries for the 3D viewer.
# These reuse the same SGP4 propagation as the screening pipeline, just
# called for a specific satellite/time on request instead of on a schedule.
# ---------------------------------------------------------------------------


def _find_satellite(norad_id: int) -> dict[str, Any] | None:
    for sat in state["satellites"]:
        if sat["norad_id"] == norad_id:
            return dict(sat)
    return None


@app.get("/positions")
def get_positions(
    norad_ids: Annotated[str, Query(description="Comma-separated NORAD IDs, e.g. '25544,36086'")],
    time: Annotated[datetime, Query(description="ISO 8601 timestamp, e.g. 2026-08-08T00:00:00Z")],
) -> dict[str, Any]:
    """Current ECI position (km) for each requested satellite at a single instant."""
    if time.tzinfo is None:
        time = time.replace(tzinfo=UTC)

    ids = [int(x) for x in norad_ids.split(",") if x.strip()]
    positions: dict[int, dict[str, float]] = {}
    missing: list[int] = []
    for norad_id in ids:
        sat = _find_satellite(norad_id)
        if sat is None:
            missing.append(norad_id)
            continue
        pos = propagate_satellite(sat["line1"], sat["line2"], [time])[0]
        if any(v != v for v in pos):  # NaN check, no numpy import needed here
            missing.append(norad_id)
            continue
        positions[norad_id] = {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])}

    return {"time": time.isoformat(), "positions": positions, "missing": missing}


class TrajectoryRequest(BaseModel):
    norad_id: int
    start_time: datetime
    duration_minutes: float = 100.0  # ~one LEO orbital period by default
    step_seconds: float = 30.0


@app.post("/trajectory")
def get_trajectory(req: TrajectoryRequest) -> dict[str, Any]:
    """Full orbit path (a sequence of ECI positions) for drawing a dotted orbit line."""
    sat = _find_satellite(req.norad_id)
    if sat is None:
        raise HTTPException(
            status_code=404,
            detail=f"No tracked satellite with NORAD ID {req.norad_id}",
        )

    start = req.start_time
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)

    times = build_time_grid(start, req.duration_minutes / 60.0, req.step_seconds)
    positions = propagate_satellite(sat["line1"], sat["line2"], times)

    points: list[dict[str, Any]] = []
    for t, pos in zip(times, positions, strict=True):
        if pos[0] != pos[0]:  # NaN check
            continue
        points.append(
            {
                "time": t.isoformat(),
                "x": float(pos[0]),
                "y": float(pos[1]),
                "z": float(pos[2]),
            }
        )

    return {"norad_id": req.norad_id, "name": sat["name"], "points": points}
