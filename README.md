# Satellite Collision Predictor

A real-time conjunction screening system that ingests live satellite orbital
data, propagates trajectories with SGP4, and flags close approaches between
tracked objects — streamed to clients over WebSocket. See
[backend/README.md](./backend/README.md) for the architecture and how to run it.

## Status

🚧 **Actively in development** — built in public, Oct 1 – Dec 11, 2026. See [ROADMAP.md](./ROADMAP.md) for the full build plan and what's shipping when.

**Current phase:** Week 0 — shared foundation (Phase 1 feature work runs Oct 5–25)
**Target launch:** Oct 25, 2026

### What works today

- FastAPI backend: TLE ingestion from CelesTrak, two-stage conjunction screening (altitude-band prefilter + pairwise propagation), risk classification that accounts for relative velocity (fixes docked-spacecraft false positives), REST + WebSocket endpoints
- `/positions` and `/trajectory` endpoints for driving a frontend visualizer

### Known gaps

- No frontend committed to this repo yet (see backend/README.md's "Known gaps" section)
- No persistence — results live in memory and reset on restart
- No automated tests or CI yet
