# Satellite Collision Predictor

A real-time conjunction screening system for tracked orbital objects. Ingests
live orbital element sets, propagates every tracked satellite's trajectory
forward with SGP4, and identifies close approaches between objects — pushed
to clients over WebSocket as new screening passes complete, no polling.

**The interesting engineering problem**: screening N satellites against each
other for close approaches is O(n²) — at 6,000 tracked objects that's ~18
million pairs, most of which are physically impossible (a satellite at 550km
altitude can never be near one at 35,000km). This system filters candidate
pairs by orbital altitude overlap *before* running expensive trajectory
propagation, cutting the search space by orders of magnitude while keeping
every geometrically possible conjunction.

## Run it

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Then visit `http://localhost:8000/docs` for interactive API docs, or
`http://localhost:8000/conjunctions` for the raw JSON.

On startup it fetches the `stations` group (~15 satellites, including the
ISS) so you get fast feedback while testing. Once it's working end to end,
bump `TRACKED_GROUP` in `app/main.py` to `"starlink"` (~6,000 satellites) —
that's where you'll actually start seeing real conjunctions, since a dense
constellation has satellites regularly passing near each other.

## How it works

1. **`tle_fetch.py`** — pulls current orbital element sets from CelesTrak
   (free, no API key).
2. **`propagate.py`** — uses SGP4 to compute each satellite's exact 3D
   position at every 30-second step over the next 24 hours.
3. **`screening.py`** — two-stage filter. Stage 1 throws out pairs whose
   orbits can't possibly cross (cheap, from the TLE alone). Stage 2
   propagates the survivors and measures real distance at every timestep.
4. **`risk.py`** — classifies each close approach by miss distance.
5. **`main.py`** — runs this on a loop, caches the results, and pushes
   updates to connected clients over `/ws/conjunctions`.

## Endpoints

- `GET /conjunctions` — current list of close-approach events, sorted by risk
- `GET /satellites` — the currently tracked satellite set
- `POST /refresh` — trigger a screening pass immediately (don't wait for the interval)
- `WS /ws/conjunctions` — live updates pushed as new passes complete

## Next steps (not built yet)

- **Persistence**: swap the in-memory `state` dict for Supabase — insert
  each event into a `conjunctions` table so you get history instead of
  just "current state." You already know the RLS patterns from Fitfolio.
- **Frontend**: Next.js dashboard consuming `/conjunctions` + the
  WebSocket, plus a 3D view (react-three-fiber) plotting satellite
  positions and highlighting the risky pairs.
- **Tuning**: `REPORT_THRESHOLD_KM` / `HIGH_RISK_KM` in `risk.py` are
  reasonable defaults, not physical laws — worth explaining in your
  README/demo why you picked them.
