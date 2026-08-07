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
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .tle_fetch import fetch_tle_group
from .propagate import build_time_grid
from .screening import find_candidate_pairs, screen_pair
from .risk import classify, is_reportable

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("collision-predictor")

TRACKED_GROUP = "stations"       # start small (~15 sats) while you're testing;
                                   # bump to "starlink" (~6000) once it's working
REFRESH_INTERVAL_SECONDS = 300    # how often to re-fetch TLEs + re-screen
SCREEN_WINDOW_HOURS = 24          # how far ahead to look for conjunctions
SCREEN_STEP_SECONDS = 30          # time resolution of the screening pass

state = {
    "satellites": [],       # last fetched TLE set
    "conjunctions": [],      # last screening results (list of dicts)
    "last_updated": None,
}
connected_clients: set[WebSocket] = set()


async def refresh_loop():
    while True:
        try:
            await run_screening_pass()
        except Exception:
            log.exception("Screening pass failed, will retry next interval")
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)


async def run_screening_pass():
    log.info(f"Fetching TLE group '{TRACKED_GROUP}'...")
    satellites = await fetch_tle_group(TRACKED_GROUP)
    log.info(f"Fetched {len(satellites)} satellites")

    times = build_time_grid(
        datetime.now(timezone.utc), SCREEN_WINDOW_HOURS, SCREEN_STEP_SECONDS
    )

    candidates = find_candidate_pairs(satellites)
    log.info(f"{len(candidates)} candidate pairs after coarse filter")

    events = []
    for sat_a, sat_b in candidates:
        result = screen_pair(sat_a, sat_b, times)
        if result and is_reportable(result["miss_distance_km"]):
            events.append({
                "sat1_norad_id": sat_a["norad_id"],
                "sat1_name": sat_a["name"],
                "sat2_norad_id": sat_b["norad_id"],
                "sat2_name": sat_b["name"],
                "time_of_closest_approach": result["time_of_closest_approach"].isoformat(),
                "miss_distance_km": round(result["miss_distance_km"], 3),
                "relative_speed_km_s": round(result["relative_speed_km_s"], 3),
                "risk_level": classify(result["miss_distance_km"], result["relative_speed_km_s"]),
            })

    events.sort(key=lambda e: e["miss_distance_km"])
    state["satellites"] = satellites
    state["conjunctions"] = events
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    log.info(f"Found {len(events)} reportable conjunctions")

    await broadcast({"type": "conjunctions_update", "data": events, "last_updated": state["last_updated"]})


async def broadcast(message: dict):
    dead = set()
    for ws in connected_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.add(ws)
    connected_clients.difference_update(dead)


@asynccontextmanager
async def lifespan(app: FastAPI):
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
def health():
    return {"status": "ok", "last_updated": state["last_updated"]}


@app.get("/satellites")
def get_satellites():
    return {"count": len(state["satellites"]), "satellites": state["satellites"]}


@app.get("/conjunctions")
def get_conjunctions():
    return {
        "count": len(state["conjunctions"]),
        "last_updated": state["last_updated"],
        "conjunctions": state["conjunctions"],
    }


@app.post("/refresh")
async def manual_refresh():
    """Trigger an immediate screening pass instead of waiting for the interval."""
    await run_screening_pass()
    return {"status": "refreshed", "count": len(state["conjunctions"])}


@app.websocket("/ws/conjunctions")
async def ws_conjunctions(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    # send current state immediately so the client doesn't wait for the next cycle
    await websocket.send_json({
        "type": "conjunctions_update",
        "data": state["conjunctions"],
        "last_updated": state["last_updated"],
    })
    try:
        while True:
            await websocket.receive_text()  # keep connection alive; ignore client msgs
    except WebSocketDisconnect:
        connected_clients.discard(websocket)
