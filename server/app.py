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

import agents
import db
import ingest
import maneuver
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
def make_plan(cdm_id: str, cascade: bool = False):
    """Solve for avoidance burns.

    cascade defaults to False because re-screening each candidate against
    the full catalog for seven days takes minutes - far too long to hold
    a request open. The solve itself is a few seconds. Run the cascade
    check separately via POST /api/plan/{id}/cascade.
    """
    if DEMO_MODE:
        return fixture(f"plan_{cdm_id}.json")

    if db.conjunction(cdm_id) is None:
        return fixture(f"plan_{cdm_id}.json")

    try:
        plan = maneuver.solve(cdm_id, run_cascade=cascade, verbose=False)
        if plan is not None:
            return plan
    except Exception as e:
        print(f"[plan] {type(e).__name__}: {e}")
    return fixture(f"plan_{cdm_id}.json")


@app.post("/api/plan/{cdm_id}/cascade")
def run_cascade(cdm_id: str, background: BackgroundTasks,
                top_n: int = 3):
    """Re-screen the top candidates' post-burn paths against the catalog.

    Backgrounded: each candidate is propagated against all 19k objects
    for seven days. The frontend polls GET /api/plan/{id} and watches
    cascade_check flip from PENDING to PASS or FAIL.
    """
    if DEMO_MODE or db.conjunction(cdm_id) is None:
        return {"state": "complete", "note": "demo mode - stored plan"}

    def job():
        try:
            maneuver.solve(cdm_id, run_cascade=True, verbose=True)
        except Exception as e:
            print(f"[cascade] {type(e).__name__}: {e}")

    background.add_task(job)
    return {"state": "running", "cdm_id": cdm_id, "top_n": top_n}


@app.post("/api/coordinate/{cdm_id}")
def coordinate(cdm_id: str):
    return fixture(f"coordinate_{cdm_id}.json")


@app.get("/api/ledger")
def ledger():
    entries = db.ledger()
    if entries and not DEMO_MODE:
        return entries
    return fixture("ledger.json")


# -------------------------------------------------------------- agents

@app.post("/api/agents/run")
def run_agents(background: BackgroundTasks, width: int = 1):
    """Run the agent pipeline in the background.

    A full run is 8-12 model calls and a couple of minutes, most of it
    cascade re-screening. The frontend watches /api/events for progress
    rather than waiting on this response.

    width is how many conjunctions to take through the full lifecycle.
    Default 1: running all sixteen would be fifty model calls and many
    minutes, which is wrong for a live demo and wrong for a free-tier
    rate limit.
    """
    if not db.has_conjunctions():
        raise HTTPException(409, "no screening results - POST /api/screen first")

    def job():
        try:
            agents.pipeline(max_conjunctions=width, verbose=True)
        except Exception as e:
            print(f"[agents] {type(e).__name__}: {e}")
            agents.emit("SYSTEM", f"Pipeline failed: {e}", level="alert")

    background.add_task(job)
    return {"state": "running", "width": width,
            "mock_agents": agents.llm.MOCK or not agents.llm.available()}


@app.post("/api/agents/{agent}")
def run_single_agent(agent: str, background: BackgroundTasks,
                     cdm_id: str = "CDM-0001"):
    """Run one agent. Useful for stepping through the demo."""
    name = agent.upper()
    if name not in agents.PROMPTS:
        raise HTTPException(404, f"unknown agent: {agent}. "
                                 f"One of {list(agents.PROMPTS)}")

    tasks = {
        "TRACKER": "Check catalog health and confirm the screening results "
                   "are fit to act on.",
        "SCREENER": "Review the current conjunctions and say whether any "
                    "response is warranted.",
        "PLANNER": f"Produce a full manoeuvre plan for {cdm_id}. Call "
                   f"assess_conjunction, then solve_maneuver, then "
                   f"rescreen_trajectory. All three are required.",
        "COORDINATOR": f"Decide who manoeuvres for {cdm_id} and publish "
                       f"the intent if the plan is clear.",
    }

    def job():
        try:
            agents.run_agent(name, tasks[name], verbose=True)
        except Exception as e:
            print(f"[{name}] {type(e).__name__}: {e}")

    background.add_task(job)
    return {"state": "running", "agent": name}


@app.get("/api/agents/status")
def agents_status():
    return {
        "mock_agents": agents.llm.MOCK or not agents.llm.available(),
        "model": agents.llm.MODEL,
        "model_calls_made": agents.llm.call_count(),
        "agents": list(agents.PROMPTS),
        "events_buffered": len(agents.BUS.history(999)),
        "providers": agents.llm.providers_status(),
    }


# -------------------------------------------------------------- events

@app.get("/api/events")
async def events(replay: int = 20):
    """Server-sent stream of agent activity.

    Unauthenticated on purpose: EventSource cannot send custom headers.

    Sends the recent history first so a client connecting mid-run still
    sees what happened, then stays open for live events. Falls back to
    replaying the fixture when nothing has run yet, so the frontend's
    feed is never empty.
    """
    q = agents.BUS.subscribe()
    history = agents.BUS.history(replay)

    async def gen():
        try:
            if history:
                for e in history:
                    yield f"data: {json.dumps(e, default=str)}\n\n"
            else:
                # Nothing has run. Replay the fixture so the panel has
                # something in it, then wait for real events.
                for e in fixture("events.json"):
                    yield f"data: {json.dumps(e)}\n\n"
                    await asyncio.sleep(0.4)

            while True:
                try:
                    e = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(e, default=str)}\n\n"
                except asyncio.TimeoutError:
                    # Comment frame keeps proxies from closing the stream.
                    yield ": keepalive\n\n"
        finally:
            agents.BUS.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/events/history")
def events_history(limit: int = 50):
    """Non-streaming version, for clients that would rather poll."""
    h = agents.BUS.history(limit)
    return h if h else fixture("events.json")


@app.post("/api/events/capture")
def events_capture():
    """Freeze the current event history as the demo fixture.

    The Gemini free tier allows twenty calls a day per model and a clean
    pipeline run is about nine, so the demo replays a captured real run.
    Call this once after a good live run.
    """
    return agents.capture()


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
        "plans": len(db.state()["plans"]),
        "ledger_entries": len(db.ledger()),
        "mock_agents": agents.llm.MOCK or not agents.llm.available(),
        "events_buffered": len(agents.BUS.history(999)),
    }
