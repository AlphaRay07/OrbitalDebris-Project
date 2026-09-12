# Aegis OTM — API contract

Single source of truth for what the backend sends the frontend.

**Rule:** when a real endpoint's output changes, the matching fixture in
`server/fixtures/` is updated in the **same commit**. Backend owns the fixtures.

Base path: `/api`. All times are ISO 8601 UTC with a `Z` suffix.
All distances in the API are **kilometres** unless the field name says `_m`.
Frontend converts to whatever the chart or globe needs at the render boundary.

---

## Two promises the backend makes

1. **Orbit tracks ship as `[lat_deg, lon_deg, alt_km]`.** Never raw ECI vectors.
   The backend does the TEME→ITRS→geodetic conversion with astropy.
2. **The covariance ellipse ships pre-solved** as semi-major, semi-minor and
   rotation. Never a 2×2 matrix. The backend runs `numpy.linalg.eigh`.

---

## `GET /api/status`
Fixture: `status.json`

Top bar and health panel.

| Field | Type | Notes |
|---|---|---|
| `catalog_objects` | int | total tracked |
| `debris_objects` | int | subset that is debris |
| `last_ingest` | iso | when CelesTrak was last pulled |
| `median_tle_age_hours` | float | catalog freshness |
| `screening.state` | enum | `idle` \| `running` \| `complete` \| `error` |
| `screening.progress` | float | 0.0–1.0, drives the progress bar |
| `screening.runtime_s` | float | how long the last run took |
| `counts` | object | `{red, amber, green}` for the header chips |
| `demo_mode` | bool | true when serving the cached scenario |
| `mock_agents` | bool | true when agent output is canned |

---

## `GET /api/conjunctions`
Fixture: `conjunctions.json` — array, pre-sorted by risk then TCA.

Left-hand threat list.

| Field | Type | Notes |
|---|---|---|
| `id` | string | `CDM-0001`, used in every other path |
| `primary` / `secondary` | object | see Object below |
| `tca` | iso | time of closest approach |
| `miss_distance_km` | float | |
| `relative_speed_kms` | float | |
| `pc` | float | collision probability, e.g. `3.2e-4` |
| `risk` | enum | `RED` \| `AMBER` \| `GREEN` |
| `status` | enum | `NEW` \| `TRIAGED` \| `PLANNED` \| `COORDINATED` \| `PUBLISHED` |
| `simulated` | bool | true for the injected demo threat — **show a badge** |

**Object:** `norad_id`, `name`, `object_type` (`PAYLOAD`/`ROCKET_BODY`/`DEBRIS`),
`size_class` (`SMALL`/`MEDIUM`/`LARGE`), `maneuverable` bool,
`operator` (string or null), `tle_age_hours` float.

**Risk bands:** RED ≥ 1e-4 · AMBER 1e-5 to 1e-4 · GREEN < 1e-5.

---

## `GET /api/conjunctions/{id}`
Fixture: `conjunction_CDM-0001.json`

Everything in the list item, plus:

| Field | Type | Notes |
|---|---|---|
| `components_m` | object | `{radial, in_track, cross_track}` miss breakdown |
| `encounter_plane` | object | see below — drives the ellipse plot |
| `pc_history` | array | `{t, pc}` for the Pc-vs-time line chart |
| `assumptions` | object | shown in a footnote; also goes on the slides |

**`encounter_plane`** — all in metres / degrees:
`miss_x_m`, `miss_y_m`, `sigma_major_m`, `sigma_minor_m`,
`rotation_deg`, `hbr_m`, `pc`.

Draw: `<ellipse>` at 1σ, a second at 3×, a `<circle>` at `hbr_m`,
and a `<line>` from origin to (`miss_x_m`, `miss_y_m`).

---

## `GET /api/ephemeris/{cdm_id}`
Fixture: `ephemeris_CDM-0001.json` — **≈750 KB, this is deliberate.**
It's the real size, so the globe and scrubber get tested under real load.

| Field | Type | Notes |
|---|---|---|
| `step_seconds` | int | 60 |
| `epochs` | string[] | 4320 entries (72h) |
| `tca_index` | int | index into `epochs` where closest approach happens |
| `tracks[]` | array | one per object |
| `tracks[].track` | array | `[lat, lon, alt_km]`, same length as `epochs` |
| `tracks[].role` | enum | `primary` \| `secondary` |

Frontend: `alt_fraction = alt_km / 6371` for globe.gl.
The scrubber is an index lookup — **do not propagate anything client-side.**

---

## `GET /api/debris-cloud`
Fixture: `debris_cloud.json`

Static visual backdrop. 300 points, capped for framerate.
`points[]` of `{lat, lon, alt_km}`.

---

## `POST /api/plan/{cdm_id}` → then `GET /api/plan/{cdm_id}`
Fixture: `plan_CDM-0001.json`

| Field | Type | Notes |
|---|---|---|
| `recommended_id` | string | highlight this dot on the Pareto chart |
| `rejected_ids` | string[] | render these differently |
| `rejection_reason` | string | **the demo's key line — display it prominently** |
| `target_pc` | float | 1e-4, draw as a threshold line |
| `propellant_estimate_g` | float | |
| `candidates[]` | array | see below |

**Candidate:** `id`, `delta_v_mms`, `direction`, `burn_epoch`, `lead_orbits`,
`new_miss_distance_km`, `new_pc`, `cascade_check` (`PASS`/`FAIL`),
`cascade_detail` (null on pass, else `{new_conjunction_with, tca,
miss_distance_km, pc}`), `feasible` bool.

Pareto chart: x = `delta_v_mms`, y = `new_pc` on a log scale.

---

## `POST /api/coordinate/{cdm_id}`
Fixture: `coordinate_CDM-0002.json`

| Field | Type | Notes |
|---|---|---|
| `both_maneuverable` | bool | false → no negotiation, show a one-liner |
| `decision.responsible_operator` | string | |
| `decision.rule_applied` | enum | `CREWED_PRIORITY` \| `ACTIVE_OVER_DERELICT` \| `LOWER_COST` |
| `decision.rule_text` | string | plain-English rule, cite it on the deciding message |
| `transcript[]` | array | `{round, from, to, message}`, max 3 rounds |

---

## `GET /api/ledger`
Fixture: `ledger.json` — array, newest last.

`seq`, `entry_hash`, `prev_hash`, `cdm_id`, `object`, `operator`,
`burn_epoch`, `delta_v_mms`, `direction`, `published_at`.

No auth. This endpoint is the "open" half of the problem statement —
demo it with a live `curl`.

---

## `GET /api/events` (SSE)
Fixture: `events.json` — an array, but the live endpoint streams these
one at a time as `data: {...}\n\n`.

| Field | Type | Notes |
|---|---|---|
| `seq` | int | monotonic |
| `ts` | iso | |
| `agent` | enum | `TRACKER` \| `SCREENER` \| `PLANNER` \| `COORDINATOR` |
| `level` | enum | `info` \| `warn` \| `alert` |
| `message` | string | one line, human-readable |
| `tool_call` | object or null | `{name, args}` — render in monospace |
| `tool_result` | object or null | collapsible |

Frontend notes: no auth on this endpoint (EventSource can't send headers),
close the connection on unmount, keep the last 100 events, and auto-scroll
only when already at the bottom.

---

## `GET /api/density`
Fixture: `density.json`

Altitude-shell histogram. `shells[]` of `{alt_min_km, alt_max_km,
object_count, conjunction_count}`.

---

## Changing the contract

Message the other person. Don't edit each other's directories.
Backend updates the fixture in the same commit as the endpoint.
