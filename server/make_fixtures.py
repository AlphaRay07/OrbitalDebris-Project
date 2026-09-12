"""Generate contract fixtures for the Aegis OTM frontend.

Run:  python make_fixtures.py
Writes JSON files into ./fixtures/

These are hand-shaped fake payloads with realistic values. The frontend
builds against these until the real endpoints are live. Whenever a real
endpoint's output changes, regenerate/edit the matching fixture in the
SAME commit so the fixtures never drift from reality.
"""

import json
import math
import os
from datetime import datetime, timedelta, timezone

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
os.makedirs(OUT, exist_ok=True)

# Anchor time for the whole fixture set. Everything is relative to this.
T0 = datetime(2026, 9, 12, 6, 0, 0, tzinfo=timezone.utc)
HORIZON_H = 72
STEP_S = 60
EARTH_R = 6371.0
EARTH_ROT_DEG_S = 360.0 / 86164.0  # sidereal


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def write(name, obj):
    path = os.path.join(OUT, name)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)
    kb = os.path.getsize(path) / 1024
    print(f"  {name:<28} {kb:>8.1f} KB")


def ground_track(inc_deg, raan_deg, alt_km, period_min, phase_deg=0.0,
                 n=None, step_s=STEP_S):
    """Simple spherical ground track. Good enough for fixtures — the real
    API returns the same shape from SGP4 + astropy TEME->ITRS."""
    if n is None:
        n = int(HORIZON_H * 3600 / step_s)
    inc = math.radians(inc_deg)
    out = []
    for k in range(n):
        t = k * step_s
        u = math.radians(phase_deg) + 2 * math.pi * t / (period_min * 60.0)
        lat = math.asin(math.sin(inc) * math.sin(u))
        dlon = math.atan2(math.cos(inc) * math.sin(u), math.cos(u))
        lon = math.radians(raan_deg) + dlon - math.radians(EARTH_ROT_DEG_S * t)
        lon = (math.degrees(lon) + 180) % 360 - 180
        # gentle altitude wobble so the frontend sees non-constant values
        alt = alt_km + 6.0 * math.sin(u * 2)
        out.append([round(math.degrees(lat), 3), round(lon, 3), round(alt, 2)])
    return out


def epochs(n, step_s=STEP_S, start=T0):
    return [iso(start + timedelta(seconds=k * step_s)) for k in range(n)]


print("writing fixtures:")

# ---------------------------------------------------------------- status
write("status.json", {
    "catalog_objects": 27431,
    "debris_objects": 14208,
    "last_ingest": iso(T0 - timedelta(minutes=14)),
    "catalog_source": "celestrak",
    "median_tle_age_hours": 8.4,
    "screening": {
        "state": "complete",       # idle | running | complete | error
        "progress": 1.0,
        "asset_id": "25544",
        "horizon_hours": HORIZON_H,
        "threshold_km": 5.0,
        "pairs_screened": 27430,
        "runtime_s": 11.8,
        "completed_at": iso(T0 - timedelta(minutes=2)),
    },
    "counts": {"red": 1, "amber": 2, "green": 4},
    "demo_mode": True,
    "mock_agents": False,
})

# --------------------------------------------------------- conjunctions
TCA_RED = T0 + timedelta(hours=31, minutes=12)


def conj(cid, name, norad, tca, miss_km, pc, risk, vrel, age_p, age_s, sim=False):
    return {
        "id": cid,
        "primary": {"norad_id": "25544", "name": "ISS (ZARYA)",
                    "object_type": "PAYLOAD", "size_class": "LARGE",
                    "maneuverable": True, "operator": "NASA",
                    "tle_age_hours": age_p},
        "secondary": {"norad_id": norad, "name": name,
                      "object_type": "DEBRIS", "size_class": "SMALL",
                      "maneuverable": False, "operator": None,
                      "tle_age_hours": age_s},
        "tca": iso(tca),
        "miss_distance_km": miss_km,
        "relative_speed_kms": vrel,
        "pc": pc,
        "risk": risk,
        "status": "TRIAGED",
        "simulated": sim,
    }


conjunctions = [
    conj("CDM-0001", "SIM-DEBRIS-001 (COSMOS 1408 DEB)", "SIM0001",
         TCA_RED, 0.412, 3.2e-4, "RED", 14.21, 6.2, 9.8, sim=True),
    conj("CDM-0002", "FENGYUN 1C DEB", "33421",
         T0 + timedelta(hours=18, minutes=41), 2.108, 4.7e-5, "AMBER",
         13.04, 6.2, 31.5),
    conj("CDM-0003", "COSMOS 2251 DEB", "34677",
         T0 + timedelta(hours=44, minutes=3), 3.377, 1.9e-5, "AMBER",
         11.86, 6.2, 14.2),
    conj("CDM-0004", "IRIDIUM 33 DEB", "34012",
         T0 + timedelta(hours=9, minutes=27), 4.219, 6.1e-6, "GREEN",
         9.55, 6.2, 22.7),
    conj("CDM-0005", "CZ-6A DEB", "58901",
         T0 + timedelta(hours=52, minutes=18), 4.640, 2.4e-6, "GREEN",
         12.73, 6.2, 5.1),
]
write("conjunctions.json", conjunctions)

# --------------------------------------------- conjunction detail (red)
write("conjunction_CDM-0001.json", {
    **conjunctions[0],
    "components_m": {"radial": -186.0, "in_track": 358.0, "cross_track": 74.0},
    "encounter_plane": {
        "miss_x_m": 240.0,
        "miss_y_m": -110.0,
        "sigma_major_m": 380.0,
        "sigma_minor_m": 95.0,
        "rotation_deg": 22.0,
        "hbr_m": 5.5,
        "pc": 3.2e-4,
    },
    "pc_history": [
        {"t": iso(T0 - timedelta(hours=h)), "pc": p}
        for h, p in [(72, 1.1e-5), (60, 2.0e-5), (48, 4.4e-5),
                     (36, 9.8e-5), (24, 1.7e-4), (12, 2.6e-4), (0, 3.2e-4)]
    ],
    "assumptions": {
        "covariance_source": "synthetic",
        "sigma_at_epoch_m": {"radial": 100, "in_track": 500, "cross_track": 100},
        "growth_exponent": 1.5,
        "hbr_source": "rcs_size_class",
    },
})

# ------------------------------------------------------------ ephemeris
n = int(HORIZON_H * 3600 / STEP_S)
write("ephemeris_CDM-0001.json", {
    "cdm_id": "CDM-0001",
    "tca": iso(TCA_RED),
    "tca_index": int((TCA_RED - T0).total_seconds() / STEP_S),
    "step_seconds": STEP_S,
    "epochs": epochs(n),
    "tracks": [
        {"object_id": "25544", "name": "ISS (ZARYA)", "role": "primary",
         "track": ground_track(51.64, 120.0, 421.0, 92.9)},
        {"object_id": "SIM0001", "name": "SIM-DEBRIS-001", "role": "secondary",
         "track": ground_track(82.60, 34.0, 418.0, 92.7, phase_deg=143.0)},
    ],
})

# ------------------------------------------------------- debris backdrop
debris = []
for i in range(300):
    a = (i * 37) % 360
    debris.append({
        "lat": round(math.degrees(math.asin(math.sin(math.radians(
            35 + (i % 60))) * math.sin(math.radians(a)))), 2),
        "lon": round(((a * 2.3 + i * 11) % 360) - 180, 2),
        "alt_km": round(420 + (i % 47) * 12.5, 1),
    })
write("debris_cloud.json", {"count": len(debris), "points": debris})

# --------------------------------------------------------------- plan
candidates = []
for i, (dv, lead, pc, miss, casc) in enumerate([
    (0.8,  0.5, 2.4e-4, 0.51, "PASS"),
    (1.5,  0.5, 1.1e-4, 0.78, "PASS"),
    (3.0,  1.0, 2.8e-5, 1.42, "PASS"),
    (4.2,  1.0, 9.6e-6, 1.98, "FAIL"),
    (6.0,  2.0, 3.1e-6, 3.11, "PASS"),
    (9.5,  2.0, 8.0e-7, 4.72, "PASS"),
    (14.0, 4.0, 1.2e-7, 9.40, "PASS"),
    (22.0, 4.0, 2.0e-8, 14.6, "PASS"),
]):
    candidates.append({
        "id": f"MNV-{i+1:03d}",
        "delta_v_mms": dv,
        "direction": "ALONG_TRACK_RETROGRADE",
        "burn_epoch": iso(TCA_RED - timedelta(hours=lead * 1.548)),
        "lead_orbits": lead,
        "new_miss_distance_km": miss,
        "new_pc": pc,
        "cascade_check": casc,
        "cascade_detail": (
            None if casc == "PASS" else
            {"new_conjunction_with": "STARLINK-4127",
             "tca": iso(TCA_RED + timedelta(days=3, hours=7)),
             "miss_distance_km": 0.81, "pc": 1.4e-4}
        ),
        "feasible": casc == "PASS" and pc <= 1e-4,
    })

write("plan_CDM-0001.json", {
    "cdm_id": "CDM-0001",
    "status": "PLANNED",
    "generated_at": iso(T0 + timedelta(minutes=3)),
    "target_pc": 1e-4,
    "recommended_id": "MNV-003",
    "rejected_ids": ["MNV-004"],
    "rejection_reason": "cascade check failed: burn creates a new conjunction with STARLINK-4127 at Pc 1.4e-4 on day 3",
    "candidates": candidates,
    "propellant_estimate_g": 42.0,
    "notes": "Along-track retrograde burn 1 orbit before TCA. Post-burn propagation uses two-body + J2.",
})

# ---------------------------------------------------------- coordinate
write("coordinate_CDM-0002.json", {
    "cdm_id": "CDM-0002",
    "status": "COORDINATED",
    "both_maneuverable": True,
    "decision": {
        "responsible_operator": "OPERATOR_B",
        "rule_applied": "CREWED_PRIORITY",
        "rule_text": "Crewed vehicles outrank active payloads; the active payload maneuvers.",
        "delta_v_mms": 3.0,
        "tie_break_used": False,
    },
    "transcript": [
        {"round": 1, "from": "OPERATOR_A", "to": "OPERATOR_B",
         "message": "Conjunction CDM-0002 at Pc 4.7e-5. Our asset is crewed. Requesting you assume maneuver responsibility."},
        {"round": 1, "from": "OPERATOR_B", "to": "OPERATOR_A",
         "message": "Acknowledged. Checking our maneuver cost before accepting."},
        {"round": 2, "from": "OPERATOR_B", "to": "OPERATOR_A",
         "message": "Our cheapest compliant burn is 3.0 mm/s, cascade check clear. Accepting responsibility under CREWED_PRIORITY."},
        {"round": 2, "from": "OPERATOR_A", "to": "OPERATOR_B",
         "message": "Confirmed. Publishing intent to the shared ledger."},
    ],
})

# ------------------------------------------------------------- ledger
write("ledger.json", [
    {"seq": 1, "entry_hash": "a3f1c8e0", "prev_hash": "00000000",
     "cdm_id": "CDM-0002", "object": "ISS (ZARYA)", "operator": "NASA",
     "burn_epoch": iso(T0 + timedelta(hours=16)), "delta_v_mms": 3.0,
     "direction": "ALONG_TRACK_RETROGRADE",
     "published_at": iso(T0 + timedelta(minutes=8))},
    {"seq": 2, "entry_hash": "7b2d90f4", "prev_hash": "a3f1c8e0",
     "cdm_id": "CDM-0001", "object": "ISS (ZARYA)", "operator": "NASA",
     "burn_epoch": iso(TCA_RED - timedelta(hours=1, minutes=33)),
     "delta_v_mms": 3.0, "direction": "ALONG_TRACK_RETROGRADE",
     "published_at": iso(T0 + timedelta(minutes=19))},
])

# ------------------------------------------------------------- density
write("density.json", {
    "shell_km": 25,
    "shells": [{"alt_min_km": 400 + i * 25, "alt_max_km": 425 + i * 25,
                "object_count": c, "conjunction_count": j}
               for i, (c, j) in enumerate([
                   (812, 3), (1104, 5), (1631, 9), (2288, 14), (2911, 21),
                   (3420, 26), (2984, 19), (2110, 11), (1502, 7), (988, 4),
                   (640, 2), (401, 1)])],
})

# -------------------------------------------------------------- events
write("events.json", [
    {"seq": 1, "ts": iso(T0), "agent": "TRACKER", "level": "info",
     "message": "Catalog refreshed from CelesTrak.",
     "tool_call": {"name": "ingest_catalog", "args": {"groups": 5}},
     "tool_result": {"objects": 27431, "median_age_h": 8.4}},
    {"seq": 2, "ts": iso(T0 + timedelta(seconds=4)), "agent": "TRACKER",
     "level": "warn", "message": "3 objects have TLEs older than 72h; covariance inflated.",
     "tool_call": None, "tool_result": None},
    {"seq": 3, "ts": iso(T0 + timedelta(seconds=9)), "agent": "SCREENER",
     "level": "info", "message": "Screening ISS against full catalog over 72h.",
     "tool_call": {"name": "screen_asset", "args": {"asset": "25544", "horizon_h": 72, "threshold_km": 5}},
     "tool_result": {"candidates": 5, "runtime_s": 11.8}},
    {"seq": 4, "ts": iso(T0 + timedelta(seconds=22)), "agent": "SCREENER",
     "level": "alert", "message": "CDM-0001 exceeds the red threshold at Pc 3.2e-4.",
     "tool_call": {"name": "compute_pc", "args": {"cdm_id": "CDM-0001"}},
     "tool_result": {"pc": 3.2e-4, "risk": "RED"}},
    {"seq": 5, "ts": iso(T0 + timedelta(seconds=31)), "agent": "PLANNER",
     "level": "info", "message": "Searching 64 burn combinations.",
     "tool_call": {"name": "solve_maneuver", "args": {"cdm_id": "CDM-0001", "target_pc": 1e-4}},
     "tool_result": {"candidates": 8, "feasible": 6}},
    {"seq": 6, "ts": iso(T0 + timedelta(seconds=47)), "agent": "PLANNER",
     "level": "alert", "message": "MNV-004 rejected: creates a new conjunction with STARLINK-4127 at 810 m.",
     "tool_call": {"name": "rescreen_ephemeris", "args": {"candidate": "MNV-004", "days": 7}},
     "tool_result": {"verdict": "FAIL", "pc": 1.4e-4}},
    {"seq": 7, "ts": iso(T0 + timedelta(seconds=52)), "agent": "PLANNER",
     "level": "info", "message": "Recommending MNV-003: 3.0 mm/s retrograde, 1 orbit before TCA.",
     "tool_call": None, "tool_result": None},
    {"seq": 8, "ts": iso(T0 + timedelta(seconds=58)), "agent": "COORDINATOR",
     "level": "info", "message": "Secondary is non-maneuverable debris; no negotiation required.",
     "tool_call": {"name": "publish_intent", "args": {"cdm_id": "CDM-0001", "mnv_id": "MNV-003"}},
     "tool_result": {"seq": 2, "entry_hash": "7b2d90f4"}},
])

print(f"\ndone -> {OUT}")
