# Roadmap — Satellite Collision Predictor

Part of a three-project build plan (Satellite Collision Predictor → LostSWE → Fitty), running Oct 1 – Dec 11, 2026. This repo is Phase 1, since it's the strongest technical signal during peak recruiting season and has the deepest architecture fix to get right early (the screening sieve).

**Goal:** a public app backed by a scheduled screening job that handles the full active catalog, with a typed API and a fast visualizer. Build order is engine → pipeline → API → frontend, so nothing downstream gets rewritten.

## Architectural traps (decided up front, not discovered later)

| Trap | Why it bites | Decision |
|---|---|---|
| All-pairs screening is O(n²) | ~10k+ active objects = ~50M pairs per timestep; a naive loop never finishes on free hosting | Three-stage sieve: apogee/perigee filter → KD-tree pairs per timestep → TCA refinement |
| Screening on request | A slow, memory-heavy job inside an API request times out and crashes small instances | Precompute in a scheduled job, store results in Postgres, the API only reads |
| TLE format + 5-digit catalog numbers | NORAD IDs are running past 99,999, which the classic TLE format can't hold | Ingest CelesTrak GP data as OMM/JSON, store `norad_id` as an integer |
| Hammering CelesTrak | CelesTrak throttles/blocks clients that refetch too often | Cache every pull with a timestamp; refuse to refetch inside a multi-hour window |
| Reference frames | SGP4 outputs TEME; the visualizer needs a consistent frame + Earth rotation, or markers drift | One frame contract (TEME → ECI for orbits, rotate Earth by GMST) before touching the visualizer |
| Server streams positions | Sending thousands of positions per frame kills the API and the browser | Server ships element sets once; browser propagates with satellite.js in a Web Worker, draws with InstancedMesh/Points |
| Overclaiming "prediction" | Miss distance from public TLEs is a screening signal, not a collision probability | Call it screening, show TLE age, add a methodology page |

## Week A — Engine correctness and scale (Oct 5–11)

| Date | Work | Push |
|---|---|---|
| Mon Oct 5 | `ARCHITECTURE.md`: frame contract, units (km, km/s, UTC ISO), component diagram | `docs: architecture and frame conventions` |
| Tue Oct 6 | Rewrite ingestion to pull CelesTrak GP data as OMM/JSON; cache + fetch throttle; integer `norad_id` | `feat(ingest): OMM ingestion with cache and fetch throttle` |
| Wed Oct 7 | Postgres via docker-compose; SQLAlchemy models + Alembic migrations (`satellites`, `element_sets`, `screening_runs`, `conjunctions`) | `feat(db): Postgres schema and migrations` |
| Thu Oct 8 | Vectorized propagation with `sgp4`'s `SatrecArray` over a time grid; benchmark vs. the current loop, record in `BENCHMARKS.md` | `perf(propagation): vectorize with SatrecArray` |
| Fri Oct 9 | Sieve stage 1: apogee/perigee overlap filter with a pad; unit tests with hand-built orbits | `feat(screening): apogee/perigee prefilter` |
| Sat Oct 10 | Sieve stage 2: `scipy.spatial.cKDTree.query_pairs` per timestep; benchmark full catalog over 24h | `feat(screening): KD-tree candidate pairs per timestep` |
| Sun Oct 11 | Sieve stage 3: TCA refinement (Brent minimization), miss distance + relative velocity; keep the docked-spacecraft filter with a regression test | `feat(screening): TCA refinement and docked-object filter` |

## Week B — Pipeline and API (Oct 12–18)

| Date | Work | Push |
|---|---|---|
| Mon Oct 12 | Risk tiers from miss distance, relative velocity, TLE age; document the heuristic and its limits in `METHODOLOGY.md` | `feat(risk): tiered screening classification` |
| Tue Oct 13 | Idempotent job `python -m app.jobs.screen`: ingest → screen → write a `screening_run` + conjunctions in one transaction | `feat(jobs): screening run CLI` |
| Wed Oct 14 | Schedule the job (cron, every 8h); log run duration and pair counts | `ci: scheduled screening job` |
| Thu Oct 15 | Endpoints: `/runs/latest`, `/conjunctions` (cursor-paginated, filter by tier), `/satellites/search`, `/satellites/{id}/elements`; Pydantic response models only | `feat(api): read-only conjunction and satellite endpoints` |
| Fri Oct 16 | Hardening: CORS allowlist, rate limiting (slowapi), cache headers, `/health`; pytest API tests against a seeded test DB | `feat(api): CORS, rate limits, caching, health check` |
| Sat Oct 17 | Dockerfile (slim, non-root), deploy API + managed Postgres, run migrations on deploy | `build: Dockerfile and production deploy` |
| Sun Oct 18 | Generate typed client from OpenAPI schema (`openapi-typescript`) into the frontend; CI fails if it drifts | `chore(web): generated API client` |

## Week C — Frontend and launch (Oct 19–25)

| Date | Work | Push |
|---|---|---|
| Mon Oct 19 | Replace ad-hoc fetches with typed client + TanStack Query; loading/error/empty states everywhere | `refactor(web): typed data fetching` |
| Tue Oct 20 | Visualizer performance: one InstancedMesh/Points for all objects, client propagation with satellite.js in a Web Worker; target 60fps with full catalog | `perf(viz): instanced rendering and worker propagation` |
| Wed Oct 21 | Conjunctions table + detail view: highlight both orbits, jump time scrubber to TCA | `feat(web): conjunction list and detail view` |
| Thu Oct 22 | Frame check: rotate Earth by GMST, verify ISS marker against a public live tracker at three timestamps | `fix(viz): consistent frames and Earth rotation` |
| Fri Oct 23 | Polish: mobile layout, keyboard access, data-freshness badge (last run, TLE age), methodology page with screening disclaimer | `feat(web): freshness badge, methodology page, a11y` |
| Sat Oct 24 | Deploy frontend to Vercel, Sentry on both tiers, Lighthouse pass; tag the release | `release: v1.0.0` |
| Sun Oct 25 | README: architecture diagram, demo GIF, benchmark numbers, trade-offs; two resume bullets with real metrics | `docs: launch README` |

## Definition of done

- [ ] Screening job runs on schedule against the full active catalog and finishes within its window
- [ ] API is read-only, rate-limited, typed and covered by pytest
- [ ] Visualizer holds smooth frame rates with every object drawn
- [ ] ISS position verified against a public tracker
- [ ] Methodology page and screening disclaimer live; TLE age shown
- [ ] README with architecture, benchmarks and demo GIF
