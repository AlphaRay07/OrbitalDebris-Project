"""Aegis OTM API.

Every endpoint has the same shape: serve live data when we have it, fall
back to the fixture otherwise. That means the frontend never sees a
missing key, and DEMO_MODE=1 pins everything to the stored scenario.

Run:  python -m uvicorn app:app --reload --port 8010
"""

import asyncio
import json
import os
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import db
import ingest
import probability
import runner

app = FastAPI(title="Aegis OTM", version="0.1")

# The frontend proxies /api through Vite, so this is belt and braces for
# the case where the teammate runs without the proxy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FIX = os.path.join(os.path.dirname(__file__), "fixtures")

# Set to 1 at hour 19 to pin every endpoint to the stored demo scenario.
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"

DEFAULT_HOURS = 72
DEFAULT_THRESHOLD_KM = 50.0

# Fields runner.py keeps for its own bookkeeping. Stripped on the way out.
INTERNAL = ("_asset_idx", "_obj_idx", "_tca_index")


# ------------------------------------------------------------- helpers

def fixture(name):
    path = os.path.join(FIX, name)
    if not os.path.exists(path):
        raise HTTPException(404, f"no fixture: {name}")
    with open(path) as f:
        return json.load(f)


def clean(record):
    """Drop internal bookkeeping fields from an outgoing record."""
    if not isinstance(record, dict):
        return record
    return {k: v for k, v in record.items() if k not in INTERNAL}


def live():
    """True when we should serve real screening results."""
    return not DEMO_MODE and db.has_conjunctions()


# -------------------------------------------------------------- status

@app.get("/api/status")
def status():
    base = fixture("status.json")
    base["demo_mode"] = DEMO_MODE

    if DEMO_MODE:
        return base

    try:
        cat = ingest.load()
    except FileNotFoundError:
        base["catalog_source"] = "no cache - run ingest.py"
        return base

    debris = sum(1 for o in cat if "deb" in o.get("_group", ""))
    cache_path = os.path.join(os.path.dirname(__file__),
                              "cache", "catalog.json")
    mtime = datetime.fromtimestamp(os.path.getmtime(cache_path),
                                   tz=timezone.utc)

    base["catalog_objects"] = len(cat)
    base["debris_objects"] = debris
    base["last_ingest"] = mtime.strftime("%Y-%m-%dT%H:%M:%SZ")

    s = db.state()["screening"]
    if s.get("state") != "idle":
        base["screening"] = s
    if db.has_conjunctions():
        base["counts"] = db.risk_counts()
    return base


# --------------------------------------------------------- conjunctions

@app.post("/api/screen")
def start_screen(background: BackgroundTasks,
                 hours: int = DEFAULT_HOURS,
                 threshold_km: float = DEFAULT_THRESHOLD_KM,
                 asset: int = runner.DEFAULT_ASSET):
    """Kick off a screening run in the background.

    Returns immediately; the frontend polls /api/status for progress. A
    full 72 hour run takes 45-60 seconds, which is far too long to hold a
    request open.
    """
    if DEMO_MODE:
        return {"state": "complete", "note": "demo mode - stored scenario"}

    if db.state()["screening"].get("state") == "running":
        return {"state": "running", "note": "already in progress"}

    def job():
        try:
            runner.run(asset_norad=asset, hours=hours,
                       threshold_km=threshold_km, verbose=True)
        except Exception as e:
            print(f"[screen] failed: {type(e).__name__}: {e}")
            db.set_state("error", 0.0)

    db.set_state("running", 0.01)
    background.add_task(job)
    return {"state": "running", "hours": hours, "threshold_km": threshold_km}


@app.get("/api/conjunctions")
def conjunctions():
    if live():
        return [clean(c) for c in db.conjunction_list()]
    return fixture("conjunctions.json")


@app.get("/api/conjunctions/{cdm_id}")
def conjunction(cdm_id: str):
    if live():
        c = db.conjunction(cdm_id)
        if c is not None:
            out = clean(c)
            out["assumptions"] = db.state().get("assumptions") \
                or probability.assumptions()
            return out
    return fixture(f"conjunction_{cdm_id}.json")


@app.get("/api/ephemeris/{cdm_id}")
def ephemeris(cdm_id: str, hours: int = DEFAULT_HOURS):
    if live():
        eph = runner.ephemeris(cdm_id, hours=hours)
        if eph is not None:
            return eph
    return fixture(f"ephemeris_{cdm_id}.json")


@app.get("/api/debris-cloud")
def debris_cloud(n: int = 300):
    if not DEMO_MODE:
        try:
            return runner.debris_cloud(n=n)
        except Exception as e:
            print(f"[debris-cloud] {type(e).__name__}: {e}")
    return fixture("debris_cloud.json")


@app.get("/api/density")
def density(shell_km: int = 25):
    if not DEMO_MODE:
        try:
            return runner.density(shell_km=shell_km)
        except Exception as e:
            print(f"[density] {type(e).__name__}: {e}")
    return fixture("density.json")


# ---------------------------------------------------------------- plan

@app.get("/api/plan/{cdm_id}")
def get_plan(cdm_id: str):
    p = db.plan(cdm_id)
    if p is not None and not DEMO_MODE:
        return p
    return fixture(f"plan_{cdm_id}.json")


@app.post("/api/plan/{cdm_id}")
def make_plan(cdm_id: str):
    # maneuver.py lands at hour 8-11. Until then the fixture stands in,
    # which keeps the frontend's planner screen fully buildable.
    return fixture(f"plan_{cdm_id}.json")


@app.post("/api/coordinate/{cdm_id}")
def coordinate(cdm_id: str):
    return fixture(f"coordinate_{cdm_id}.json")


@app.get("/api/ledger")
def ledger():
    entries = db.ledger()
    if entries and not DEMO_MODE:
        return entries
    return fixture("ledger.json")


# -------------------------------------------------------------- events

@app.get("/api/events")
async def events():
    """Server-sent event stream of agent activity.

    Unauthenticated on purpose: EventSource cannot send custom headers.
    Replays the fixture until the agent layer lands at hour 11-13.
    """
    async def gen():
        for e in fixture("events.json"):
            yield f"data: {json.dumps(e)}\n\n"
            await asyncio.sleep(1.5)
        yield "data: {\"seq\": 0, \"agent\": \"SYSTEM\", \"level\": \"info\", " \
              "\"message\": \"stream complete\", \"tool_call\": null, " \
              "\"tool_result\": null}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------------------------------------------------------------- meta

@app.get("/api/assumptions")
def assumptions():
    """Stated limitations. Shown in the UI footnote and on the slides."""
    return db.state().get("assumptions") or probability.assumptions()


@app.get("/api/health")
def health():
    s = db.state()["screening"]
    return {
        "ok": True,
        "demo_mode": DEMO_MODE,
        "serving": "fixtures" if not live() else "live",
        "screening_state": s.get("state"),
        "conjunctions": len(db.state()["order"]),
    }