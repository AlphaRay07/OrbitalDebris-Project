"""Screening result store for Aegis OTM.

Screening takes 20-40 seconds, so it cannot run per request. Results live
in a module-level dict, backed by a JSON file on disk so that uvicorn's
--reload does not wipe them every time you save a file.

Not a real database. Deliberately - SQLite would cost a schema and a
layer of code for no benefit at this scale.
"""

import json
import os
from datetime import datetime, timezone

STORE_PATH = os.path.join(os.path.dirname(__file__), "cache", "screening.json")

_state = None


def _blank():
    return {
        "screening": {
            "state": "idle",
            "progress": 0.0,
            "asset_id": None,
            "horizon_hours": None,
            "threshold_km": None,
            "pairs_screened": 0,
            "runtime_s": None,
            "completed_at": None,
        },
        "asset": None,
        "conjunctions": {},      # cdm_id -> full record
        "order": [],             # cdm_ids, risk then TCA
        "plans": {},             # cdm_id -> plan record
        "ledger": [],
        "assumptions": {},
    }


def state():
    """Load once, then serve from memory."""
    global _state
    if _state is None:
        try:
            with open(STORE_PATH) as f:
                _state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _state = _blank()
    return _state


def save():
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    with open(STORE_PATH, "w") as f:
        json.dump(state(), f)


def reset():
    global _state
    _state = _blank()
    save()


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------ accessors

def has_conjunctions():
    return bool(state()["order"])


def conjunction_list():
    """Summary records for the threat list, in ranked order."""
    s = state()
    out = []
    for cid in s["order"]:
        c = s["conjunctions"][cid]
        out.append({k: c[k] for k in (
            "id", "primary", "secondary", "tca", "miss_distance_km",
            "relative_speed_kms", "pc", "risk", "status", "simulated")})
    return out


def conjunction(cdm_id):
    return state()["conjunctions"].get(cdm_id)


def risk_counts():
    s = state()
    counts = {"red": 0, "amber": 0, "green": 0}
    for cid in s["order"]:
        counts[s["conjunctions"][cid]["risk"].lower()] += 1
    return counts


def put_screening(screening, asset, conjunctions, assumptions):
    """Replace the whole screening result set."""
    s = state()
    s["screening"] = screening
    s["asset"] = asset
    s["assumptions"] = assumptions
    s["conjunctions"] = {c["id"]: c for c in conjunctions}
    s["order"] = [c["id"] for c in conjunctions]
    save()


def set_state(name, progress=0.0):
    s = state()
    s["screening"]["state"] = name
    s["screening"]["progress"] = progress
    save()


def put_plan(cdm_id, plan):
    s = state()
    s["plans"][cdm_id] = plan
    if cdm_id in s["conjunctions"]:
        s["conjunctions"][cdm_id]["status"] = "PLANNED"
    save()


def plan(cdm_id):
    return state()["plans"].get(cdm_id)


def append_ledger(entry):
    s = state()
    entry["seq"] = len(s["ledger"]) + 1
    s["ledger"].append(entry)
    save()
    return entry


def ledger():
    return state()["ledger"]
