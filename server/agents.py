"""Agent orchestration for Aegis OTM.

Four agents, each owning one transition of a conjunction's lifecycle:

    NEW -> TRIAGED -> PLANNED -> COORDINATED -> PUBLISHED
            ^           ^            ^             ^
         SCREENER    PLANNER    COORDINATOR   COORDINATOR

TRACKER sits outside that chain and watches catalog health.

Deliberately a plain async state machine rather than an agent framework.
Debugging someone else's graph library at 3am has ended more hackathon
projects than bad ideas have.

The rule that makes this defensible: the model never does arithmetic. It
decides which tool to call and writes the explanation. Every number comes
from tools.py, which wraps code validated against external references.

Run directly:  python agents.py            (full pipeline, top conjunction)
               python agents.py TRACKER    (one agent)
               python agents.py --all 3    (top 3 conjunctions)
"""

import asyncio
import json
import time

import db
import llm
import tools

MAX_CONJUNCTIONS = 1        # default pipeline width - see notes below

# Appended to every prompt. The agent feed is a live panel in the UI, not
# a document - markdown headers and LaTeX render as literal characters
# there, so they have to be suppressed at the source.
STYLE = """

Output style: plain prose only. No markdown headers, no bullet lists, no
bold, no LaTeX. Write numbers in plain notation - 2.5e-11, not
$2.5 \\times 10^{-11}$. Keep it to a few sentences; your output appears in
a live operations feed, not a report."""

PROMPTS = {

    "TRACKER": """You are TRACKER, the catalog health agent in an orbital
traffic management system.

Your job: check that the tracked object catalog is current and fit to
screen against, and say so plainly. Look at how many objects are loaded,
how stale the tracking data is, and whether a screening run is needed.

Call get_catalog_status first. Only call screen_catalog if there are no
conjunctions on file or the last screening is clearly stale - it takes
about a minute.

Report in two or three sentences. Flag anything that would undermine
confidence in the screening results, especially stale element sets.

Never calculate anything yourself. Every number you state must have come
from a tool result.""",

    "SCREENER": """You are SCREENER, the conjunction assessment agent in an
orbital traffic management system.

Your job: review the close approaches found by screening, identify which
matter, and explain why. Call get_conjunctions, then assess_conjunction on
the highest-risk one for detail.

Risk bands: RED is collision probability at or above 1e-4, AMBER 1e-5 to
1e-4, GREEN below 1e-5.

Be honest when nothing is dangerous. A quiet week is the normal case and
saying so is more useful than manufacturing concern. If every conjunction
is GREEN, say that clearly and name the closest one.

Report in three or four sentences: what was found, which is closest, and
whether any response is warranted.

Never calculate anything yourself. Every number you state must have come
from a tool result.""",

    "PLANNER": """You are PLANNER, the manoeuvre planning agent in an
orbital traffic management system.

Your job: for a given conjunction, find an avoidance burn and justify it.

Sequence:
  1. assess_conjunction to understand the geometry
  2. solve_maneuver to search the burn options
  3. rescreen_trajectory to run the cascade check

The cascade check is not optional. A burn that moves you out of one
object's path and into another's is not a solution, and you must not
recommend a candidate that has failed it.

Explain the recommendation in terms an operator cares about: how much
delta-v, how far ahead of closest approach, how much extra separation it
buys, and what the cascade check found.

If no burn meaningfully improves the situation, say so. On a wide
conjunction that is the correct answer - small burns cannot close
kilometre-scale gaps, and pretending otherwise is worse than nothing.

Never calculate anything yourself. Every number you state must have come
from a tool result.""",

    "COORDINATOR": """You are COORDINATOR, the traffic deconfliction agent
in an orbital traffic management system.

Your job: decide who manoeuvres, then publish the intent to the open
ledger so other operators can see it.

Right of way, in order:
  1. Crewed vehicles outrank everything
  2. Active payloads outrank derelict objects and debris
  3. If both parties rank equally, whoever can manoeuvre more cheaply moves

Debris cannot manoeuvre, so when the secondary object is debris there is
nothing to negotiate - the active satellite moves and you say so in one
line.

Call get_plan to see the recommendation. Only call publish_intent once the
plan has passed the cascade check. State which rule you applied.

Never calculate anything yourself. Every number you state must have come
from a tool result.""",
}


PROMPTS = {k: v + STYLE for k, v in PROMPTS.items()}


# ------------------------------------------------------------- event bus

class EventBus:
    """Fan-out queue for agent activity.

    Subscribers are the SSE connections in app.py. History is kept so a
    client connecting mid-run still sees what happened.
    """

    def __init__(self, history_size=200):
        self._subs = []
        self._history = []
        self._history_size = history_size
        self._seq = 0

    def publish(self, event):
        self._seq += 1
        event["seq"] = self._seq
        event.setdefault("ts", db.now_iso())

        self._history.append(event)
        if len(self._history) > self._history_size:
            self._history = self._history[-self._history_size:]

        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
        return event

    def subscribe(self):
        q = asyncio.Queue(maxsize=100)
        self._subs.append(q)
        return q

    def unsubscribe(self, q):
        if q in self._subs:
            self._subs.remove(q)

    def history(self, limit=50):
        return self._history[-limit:]

    def clear(self):
        self._history = []
        self._seq = 0


BUS = EventBus()


def emit(agent, message, level="info", tool_call=None, tool_result=None):
    return BUS.publish({
        "agent": agent,
        "level": level,
        "message": message,
        "tool_call": tool_call,
        "tool_result": tool_result,
    })


# ---------------------------------------------------------------- agents

def truncate(obj, limit=600):
    """Tool results can be large. The feed needs a readable summary."""
    s = json.dumps(obj, default=str)
    return json.loads(s) if len(s) <= limit else {
        "_truncated": True,
        "_size": len(s),
        "_preview": s[:limit] + "...",
    }


def run_agent(agent, task, verbose=True):
    """One agent turn. Returns {"text", "tool_calls", "rounds"}."""
    schemas = tools.schemas_for(agent)
    dispatch = tools.dispatch_for(agent)

    def on_event(e):
        if e["type"] == "tool_call":
            emit(agent, f"calling {e['name']}", level="info",
                 tool_call={"name": e["name"], "args": e["args"]})
        else:
            result = e["result"]
            level = "warn" if isinstance(result, dict) and "error" in result \
                else "info"
            emit(agent, f"{e['name']} returned", level=level,
                 tool_result=truncate(result))

    emit(agent, task, level="info")

    t0 = time.time()
    try:
        out = llm.llm_call(
            system=PROMPTS[agent],
            messages=[{"role": "user", "text": task}],
            tool_schemas=schemas,
            dispatch=dispatch,
            on_event=on_event,
        )
    except llm.LLMError as e:
        emit(agent, f"LLM call failed: {e}", level="alert")
        return {"text": "", "tool_calls": [], "rounds": 0, "error": str(e)}

    elapsed = time.time() - t0
    emit(agent, out["text"] or "(no text)", level="info")

    if verbose:
        mode = " [mock]" if out.get("mock") else ""
        print(f"\n[{agent}]{mode} {out['rounds']} round(s), "
              f"{len(out['tool_calls'])} tool call(s), {elapsed:.1f}s")
        for c in out["tool_calls"]:
            print(f"  -> {c['name']}({json.dumps(c['args'], default=str)})")
        print(f"  {out['text']}")

    return out


# --------------------------------------------------------- state machine

TRANSITIONS = [
    ("NEW", "TRIAGED", "SCREENER"),
    ("TRIAGED", "PLANNED", "PLANNER"),
    ("PLANNED", "PUBLISHED", "COORDINATOR"),
]


def set_status(cdm_id, status):
    s = db.state()
    if cdm_id in s["conjunctions"]:
        s["conjunctions"][cdm_id]["status"] = status
        db.save()


def pipeline(max_conjunctions=MAX_CONJUNCTIONS, verbose=True):
    """Run the full lifecycle.

    Width defaults to one conjunction. Running all sixteen would be fifty
    API calls and several minutes of cascade checks - fine as a batch job,
    wrong for a live demo and wrong for a free-tier rate limit.
    """
    t0 = time.time()
    BUS.clear()
    emit("SYSTEM", "Pipeline started", level="info")

    results = {"agents": [], "conjunctions": []}

    # TRACKER runs once, outside the per-conjunction chain.
    results["agents"].append(
        {"agent": "TRACKER", **run_agent(
            "TRACKER",
            "Check catalog health and confirm whether the current screening "
            "results are fit to act on.",
            verbose=verbose)})

    rows = db.conjunction_list()
    if not rows:
        emit("SYSTEM", "No conjunctions on file - nothing to assess",
             level="warn")
        return results

    # SCREENER reviews the whole set once.
    results["agents"].append(
        {"agent": "SCREENER", **run_agent(
            "SCREENER",
            "Review the current conjunctions. Identify the highest-risk "
            "one and say whether any response is warranted.",
            verbose=verbose)})

    targets = rows[:max_conjunctions]
    for row in targets:
        cdm_id = row["id"]
        emit("SYSTEM", f"Processing {cdm_id} ({row['secondary']['name']})",
             level="info")

        set_status(cdm_id, "TRIAGED")

        plan_out = run_agent(
            "PLANNER",
            f"Plan an avoidance manoeuvre for {cdm_id}. Assess the "
            f"geometry, search the burn options, and run the cascade "
            f"check before recommending anything.",
            verbose=verbose)
        set_status(cdm_id, "PLANNED")

        coord_out = run_agent(
            "COORDINATOR",
            f"Decide who manoeuvres for {cdm_id} and publish the intent to "
            f"the ledger if the plan has passed its cascade check.",
            verbose=verbose)

        published = any(
            c["name"] == "publish_intent"
            and isinstance(c["result"], dict)
            and c["result"].get("published") is True
            for c in coord_out.get("tool_calls", []))
        set_status(cdm_id, "PUBLISHED" if published else "COORDINATED")

        results["conjunctions"].append({
            "cdm_id": cdm_id,
            "object": row["secondary"]["name"],
            "planner": plan_out["text"],
            "coordinator": coord_out["text"],
            "published": published,
        })

    elapsed = time.time() - t0
    emit("SYSTEM", f"Pipeline complete in {elapsed:.0f}s "
                   f"({llm.call_count()} model calls)", level="info")
    results["elapsed_s"] = round(elapsed, 1)
    results["model_calls"] = llm.call_count()
    return results


# ------------------------------------------------------------- capture

def capture(path=None, limit=999):
    """Freeze the current event history into fixtures/events.json.

    The free tier allows twenty model calls a day per model, and a clean
    pipeline run is about nine. So the demo runs off a captured real run
    rather than a live one - disclose that, it is the normal answer to a
    rate-limited dependency.

    Workflow:
        MOCK_AGENTS=0  python agents.py          (one good live run)
        python agents.py --capture               (freeze it)
        DEMO_MODE=1                              (replay it)
    """
    import os

    if path is None:
        path = os.path.join(os.path.dirname(__file__),
                            "fixtures", "events.json")

    history = BUS.history(limit)
    if not history:
        return {"error": "no events in memory - run the pipeline first"}

    with open(path, "w") as f:
        json.dump(history, f, indent=2)

    return {"written": path, "events": len(history),
            "agents": sorted({e["agent"] for e in history})}


def replay_source():
    """Where /api/events would currently get its data from."""
    return "live" if BUS.history(1) else "fixture"


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]

    if "--capture" in args:
        print(json.dumps(capture(), indent=2))
        raise SystemExit(0)

    if args and args[0].upper() in PROMPTS:
        agent = args[0].upper()
        tasks = {
            "TRACKER": "Check catalog health.",
            "SCREENER": "Review the current conjunctions and rank the risk.",
            "PLANNER": "Plan an avoidance manoeuvre for CDM-0001.",
            "COORDINATOR": "Decide who manoeuvres for CDM-0001 and publish "
                           "the intent if the plan is clear.",
        }
        print(f"mock mode: {llm.MOCK or not llm.available()}\n")
        run_agent(agent, tasks[agent])
        raise SystemExit(0)

    width = MAX_CONJUNCTIONS
    if "--all" in args:
        i = args.index("--all")
        width = int(args[i + 1]) if len(args) > i + 1 else 3

    if not db.has_conjunctions():
        raise SystemExit("no screening results - run: python runner.py 72 50")

    print(f"mock mode  : {llm.MOCK or not llm.available()}")
    print(f"model      : {llm.MODEL}")
    print(f"width      : {width} conjunction(s)")
    print("-" * 70)

    out = pipeline(max_conjunctions=width)

    print("\n" + "=" * 70)
    print(f"pipeline finished in {out.get('elapsed_s')}s, "
          f"{out.get('model_calls')} model calls")

    for c in out["conjunctions"]:
        print(f"\n{c['cdm_id']}  {c['object']}")
        print(f"  published: {c['published']}")

    print(f"\nledger has {len(db.ledger())} entries")
    for e in db.ledger()[-3:]:
        print(f"  #{e['seq']} {e['entry_hash']} {e.get('maneuver_id')} "
              f"{e.get('delta_v_mms')} mm/s")

    n = len(BUS.history(999))
    print(f"\n{n} events emitted (these stream to the UI via /api/events)")

    if not (llm.MOCK or not llm.available()):
        print("\nThat was a live run. Freeze it as the demo fixture with:")
        print("  python agents.py --capture")