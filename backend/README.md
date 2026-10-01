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

\`\`\`bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
\`\`\`

Then visit \`http://localhost:8000/docs\` for interactive API docs, or
\`http://localhost:8000/conjunctions\` for the raw JSON.

On startup it fetches the \`stations\` group (~15 satellites, including the
ISS) so you get fast feedback while testing. Once it's working end to end,
bump \`TRACKED_GROUP\` in \`app/main.py\` to \`"starlink"\` (~6,000 satellites) —
that's where you'll actually start seeing real conjunctions, since a dense
constellation has satellites regularly passing near each other.

## How it works

1. **\`tle_fetch.py\`** — pulls current orbital element sets from CelesTrak
   (free, no API key).
2. **\`propagate.py\`** — uses SGP4 to compute each satellite's exact 3D
   position at every 30-second step over the next 24 hours.
3. **\`screening.py\`** — two-stage filter. Stage 1 throws out pairs whose
   orbits can't possibly cross (cheap, from the TLE alone). Stage 2
   propagates the survivors and measures real distance at every timestep.
4. **\`risk.py\`** — classifies each close approach by miss distance *and*
   relative velocity, so two objects passing at 0 km but near-zero relative
   speed (docked spacecraft, formation flyers) are tagged \`co-orbiting\`
   instead of a false-positive \`high\` risk.
5. **\`main.py\`** — runs this on a loop, caches the results, and pushes
   updates to connected clients over \`/ws/conjunctions\`.

## Endpoints

- \`GET /conjunctions\` — current list of close-approach events, sorted by risk
- \`GET /satellites\` — the currently tracked satellite set
- \`GET /positions?norad_ids=...&time=...\` — current ECI position for a set of satellites at one instant
- \`POST /trajectory\` — full orbit path for a single satellite, for drawing an orbit line
- \`POST /refresh\` — trigger a screening pass immediately (don't wait for the interval)
- \`GET /health\` — liveness check
- \`WS /ws/conjunctions\` — live updates pushed as new passes complete

## Known gaps (tracked as GitHub issues)

- **Frontend was never committed.** A vanilla Three.js visualizer (full
  solar system + Earth view, satellite tracking, time slider) was built in
  an earlier session but exists only as files the user downloaded —
  never added to this repo. The Week C rebuild (Oct 19–25, see
  \`../ROADMAP.md\`) replaces it with a typed-client version anyway, so this
  is tracked as a gap rather than recovered as-is.
- **Persistence**: the in-memory \`state\` dict means a restart loses all
  history. The Week A/B roadmap tasks (Oct 7, Oct 13) replace this with
  Postgres + a scheduled screening job.
- **Tuning**: \`REPORT_THRESHOLD_KM\` / \`HIGH_RISK_KM\` / \`COORBITING_SPEED_KM_S\`
  in \`risk.py\` are reasonable defaults, not physical laws — worth
  explaining in the README/demo why they were picked.
