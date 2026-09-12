"""Tools the agents can call.

This is the whole boundary between the language model and the physics.
Every tool here wraps code that has been validated against an external
reference - ISS altitude against reality, Pc against a closed form,
geodetic against astropy, manoeuvre shift against 3*dv*T. The model
chooses what to call and writes the prose; it never produces a number.

Each tool has a JSON schema (what the model sees) and an implementation
(what actually runs). TOOLS groups them by agent so each agent only gets
the tools it should have - a Screener that can publish to the ledger is
a Screener that eventually will.

Run directly to self-test:  python tools.py
"""

import db
import ingest
import maneuver
import probability
import runner

# --------------------------------------------------------------- schemas

SCHEMAS = {

    "get_catalog_status": {
        "name": "get_catalog_status",
        "description": (
            "Current state of the tracked object catalog: how many objects, "
            "how many are debris, when it was last refreshed, and how stale "
            "the tracking data is. Use this to judge catalog health before "
            "trusting any screening result."),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },

    "screen_catalog": {
        "name": "screen_catalog",
        "description": (
            "Screen one asset satellite against every tracked object and "
            "return close approaches. Slow - takes about a minute - so only "
            "call this when there are no current results or they are stale."),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_norad_id": {
                    "type": "string",
                    "description": "NORAD catalog number, e.g. 25544 for the ISS.",
                },
                "horizon_hours": {
                    "type": "integer",
                    "description": "How far ahead to look. 72 is standard.",
                },
                "threshold_km": {
                    "type": "number",
                    "description": "Report approaches closer than this.",
                },
            },
            "required": ["asset_norad_id"],
        },
    },

    "get_conjunctions": {
        "name": "get_conjunctions",
        "description": (
            "List the close approaches found by the last screening run, "
            "already ranked by risk then collision probability. Returns "
            "object names, miss distances, closing speeds, collision "
            "probabilities and risk bands. Note that 'returned' is a page "
            "size - use 'total_on_file' when stating how many conjunctions "
            "exist."),
        "input_schema": {
            "type": "object",
            "properties": {
                "risk": {
                    "type": "string",
                    "enum": ["ALL", "RED", "AMBER", "GREEN"],
                    "description": "Filter by risk band.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number to return.",
                },
            },
            "required": [],
        },
    },

    "assess_conjunction": {
        "name": "assess_conjunction",
        "description": (
            "Full detail for one close approach: the miss vector broken "
            "into radial, in-track and cross-track components, the "
            "encounter-plane uncertainty ellipse, the collision "
            "probability, and the stated assumptions behind it."),
        "input_schema": {
            "type": "object",
            "properties": {
                "cdm_id": {
                    "type": "string",
                    "description": "Conjunction identifier, e.g. CDM-0001.",
                },
            },
            "required": ["cdm_id"],
        },
    },

    "solve_maneuver": {
        "name": "solve_maneuver",
        "description": (
            "Search for collision avoidance burns. Evaluates 96 options "
            "across a range of burn magnitudes, lead times and both "
            "along-track directions, and returns them ranked by how much "
            "separation they gain. Does not run the cascade check - call "
            "rescreen_trajectory for that."),
        "input_schema": {
            "type": "object",
            "properties": {
                "cdm_id": {
                    "type": "string",
                    "description": "Conjunction identifier to plan against.",
                },
                "target_pc": {
                    "type": "number",
                    "description": (
                        "Collision probability to get under. 0.0001 is the "
                        "standard operational threshold."),
                },
            },
            "required": ["cdm_id"],
        },
    },

    "rescreen_trajectory": {
        "name": "rescreen_trajectory",
        "description": (
            "Check whether a proposed avoidance burn creates a NEW close "
            "approach. Propagates the post-burn trajectory forward and "
            "screens it against the whole catalog for seven days. A burn "
            "that dodges one object into the path of another is not a "
            "solution. Slow - about a minute per candidate."),
        "input_schema": {
            "type": "object",
            "properties": {
                "cdm_id": {"type": "string",
                           "description": "Conjunction identifier."},
            },
            "required": ["cdm_id"],
        },
    },

    "get_plan": {
        "name": "get_plan",
        "description": (
            "Retrieve the manoeuvre plan already computed for a "
            "conjunction, including which candidate is recommended and "
            "whether any were rejected by the cascade check."),
        "input_schema": {
            "type": "object",
            "properties": {
                "cdm_id": {"type": "string",
                           "description": "Conjunction identifier."},
            },
            "required": ["cdm_id"],
        },
    },

    "publish_intent": {
        "name": "publish_intent",
        "description": (
            "Publish a manoeuvre to the open, append-only coordination "
            "ledger so other operators can see what this satellite intends "
            "to do. Only call this once a plan has passed the cascade "
            "check and responsibility has been settled."),
        "input_schema": {
            "type": "object",
            "properties": {
                "cdm_id": {"type": "string",
                           "description": "Conjunction identifier."},
                "maneuver_id": {
                    "type": "string",
                    "description": "Which candidate to publish, e.g. MNV-003.",
                },
                "operator": {
                    "type": "string",
                    "description": "Operator taking responsibility for the burn.",
                },
            },
            "required": ["cdm_id", "maneuver_id"],
        },
    },

    "get_ledger": {
        "name": "get_ledger",
        "description": (
            "Read the open coordination ledger: every manoeuvre intent "
            "published so far, hash-chained so entries cannot be altered."),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
}


# Each agent gets only the tools it needs.
TOOLS = {
    "TRACKER": ["get_catalog_status", "screen_catalog"],
    "SCREENER": ["get_conjunctions", "assess_conjunction"],
    "PLANNER": ["assess_conjunction", "solve_maneuver",
                "rescreen_trajectory", "get_plan"],
    "COORDINATOR": ["get_plan", "publish_intent", "get_ledger"],
}


def schemas_for(agent):
    """Tool schemas for one agent, in the shape llm_call expects."""
    return [SCHEMAS[n] for n in TOOLS.get(agent, [])]


# -------------------------------------------------------- implementations

def sig(x, digits=3):
    """Round to significant figures for anything a model will read aloud.

    Collision probabilities span 300 orders of magnitude, so a raw float
    comes back as 2.47294444207114e-11 and the model echoes every digit
    into the operations feed. Three significant figures is all the
    precision the number actually carries.
    """
    if x is None:
        return None
    try:
        return float(f"{float(x):.{digits}g}")
    except (TypeError, ValueError):
        return x

def _get_catalog_status():
    try:
        cat = ingest.load()
    except FileNotFoundError:
        return {"error": "no catalog cached - run ingest.py"}

    ages = [probability.epoch_age_hours(o.get("EPOCH")) for o in cat[:2000]]
    ages.sort()
    median = ages[len(ages) // 2] if ages else None
    stale = sum(1 for a in ages if a > 72)

    s = db.state()["screening"]
    return {
        "catalog_objects": len(cat),
        "debris_objects": sum(1 for o in cat if "deb" in o.get("_group", "")),
        "median_tle_age_hours": round(median, 1) if median else None,
        "objects_with_stale_tles": stale,
        "last_screening_state": s.get("state"),
        "last_screening_completed": s.get("completed_at"),
        "conjunctions_on_file": len(db.state()["order"]),
    }


def _screen_catalog(asset_norad_id, horizon_hours=72, threshold_km=50.0):
    summary = runner.run(asset_norad=int(asset_norad_id),
                         hours=int(horizon_hours),
                         threshold_km=float(threshold_km),
                         verbose=False)
    return {
        "state": summary["state"],
        "objects_screened": summary["pairs_screened"],
        "runtime_seconds": summary["runtime_s"],
        "conjunctions_found": len(db.state()["order"]),
        "risk_counts": db.risk_counts(),
    }


def _get_conjunctions(risk="ALL", limit=10):
    rows = db.conjunction_list()
    total = len(rows)
    if risk and risk != "ALL":
        rows = [r for r in rows if r["risk"] == risk]
    matching = len(rows)
    rows = rows[:int(limit)]
    # Three separate counts, because a model given only a page size will
    # report the page size as the total.
    return {
        "total_on_file": total,
        "matching_filter": matching,
        "returned": len(rows),
        "conjunctions": [{
            "cdm_id": r["id"],
            "object": r["secondary"]["name"],
            "object_type": r["secondary"]["object_type"],
            "maneuverable": r["secondary"]["maneuverable"],
            "tca": r["tca"],
            "miss_distance_km": sig(r["miss_distance_km"], 4),
            "closing_speed_kms": sig(r["relative_speed_kms"], 4),
            "collision_probability": sig(r["pc"]),
            "risk": r["risk"],
        } for r in rows],
    }


def _assess_conjunction(cdm_id):
    c = db.conjunction(cdm_id)
    if c is None:
        return {"error": f"{cdm_id} not found"}
    return {
        "cdm_id": c["id"],
        "primary": c["primary"]["name"],
        "secondary": c["secondary"]["name"],
        "secondary_maneuverable": c["secondary"]["maneuverable"],
        "tca": c["tca"],
        "hours_to_tca": c.get("lead_hours"),
        "miss_distance_km": sig(c["miss_distance_km"], 4),
        "closing_speed_kms": sig(c["relative_speed_kms"], 4),
        "miss_components_m": {k: sig(v, 4)
                              for k, v in (c.get("components_m") or {}).items()},
        "encounter_plane": {k: sig(v, 4)
                            for k, v in (c.get("encounter_plane") or {}).items()},
        "collision_probability": sig(c["pc"]),
        "risk": c["risk"],
        "tle_age_hours": {
            "primary": c["primary"].get("tle_age_hours"),
            "secondary": c["secondary"].get("tle_age_hours"),
        },
        "assumptions": probability.assumptions(),
    }


def _solve_maneuver(cdm_id, target_pc=1e-4):
    plan = maneuver.solve(cdm_id, target_pc=float(target_pc),
                          run_cascade=False, verbose=False)
    if plan is None:
        return {"error": f"could not plan for {cdm_id}"}

    helpful = [c for c in plan["candidates"] if c["miss_gain_km"] > 0]
    helpful.sort(key=lambda c: -c["miss_gain_km"])

    return {
        "cdm_id": cdm_id,
        "baseline_miss_km": sig(plan["baseline_miss_km"], 4),
        "baseline_pc": sig(plan["baseline_pc"]),
        "candidates_evaluated": len(plan["candidates"]),
        "candidates_that_help": len(helpful),
        "recommended_id": plan["recommended_id"],
        "top_options": [{
            "maneuver_id": c["id"],
            "delta_v_mms": c["delta_v_mms"],
            "direction": c["direction"],
            "burn_epoch": c["burn_epoch"],
            "lead_orbits": c["lead_orbits"],
            "new_miss_distance_km": sig(c["new_miss_distance_km"], 4),
            "separation_gained_km": sig(c["miss_gain_km"], 3),
            "new_collision_probability": sig(c["new_pc"]),
            "propellant_grams": sig(c["propellant_g"], 4),
            "cascade_check": c["cascade_check"],
        } for c in helpful[:5]],
        "note": plan["notes"],
    }


def _rescreen_trajectory(cdm_id):
    plan = maneuver.solve(cdm_id, run_cascade=True, verbose=False)
    if plan is None:
        return {"error": f"could not plan for {cdm_id}"}

    checked = [c for c in plan["candidates"]
               if c["cascade_check"] != "PENDING"]
    return {
        "cdm_id": cdm_id,
        "candidates_checked": len(checked),
        "recommended_id": plan["recommended_id"],
        "rejected_ids": plan["rejected_ids"],
        "rejection_reason": plan["rejection_reason"],
        "results": [{
            "maneuver_id": c["id"],
            "delta_v_mms": c["delta_v_mms"],
            "verdict": c["cascade_check"],
            "new_conjunction": ({k: sig(v) if isinstance(v, (int, float))
                                 else v
                                 for k, v in c["cascade_detail"].items()}
                                if c["cascade_detail"] else None),
        } for c in checked],
    }


def _get_plan(cdm_id):
    plan = db.plan(cdm_id)
    if plan is None:
        return {"error": f"no plan for {cdm_id} - call solve_maneuver first"}
    rec = next((c for c in plan["candidates"]
                if c["id"] == plan["recommended_id"]), None)
    return {
        "cdm_id": cdm_id,
        "status": plan["status"],
        "recommended": rec,
        "rejected_ids": plan["rejected_ids"],
        "rejection_reason": plan["rejection_reason"],
        "baseline_miss_km": plan.get("baseline_miss_km"),
    }


def _publish_intent(cdm_id, maneuver_id, operator="UNSPECIFIED"):
    import hashlib

    plan = db.plan(cdm_id)
    if plan is None:
        return {"error": f"no plan for {cdm_id}"}
    cand = next((c for c in plan["candidates"] if c["id"] == maneuver_id),
                None)
    if cand is None:
        return {"error": f"{maneuver_id} not in the plan for {cdm_id}"}
    if cand["cascade_check"] == "FAIL":
        return {"error": f"{maneuver_id} failed the cascade check and "
                         f"cannot be published"}

    c = db.conjunction(cdm_id)
    existing = db.ledger()
    prev = existing[-1]["entry_hash"] if existing else "00000000"

    payload = (f"{prev}|{cdm_id}|{maneuver_id}|{cand['burn_epoch']}"
               f"|{cand['delta_v_mms']}")
    entry_hash = hashlib.sha256(payload.encode()).hexdigest()[:8]

    entry = db.append_ledger({
        "entry_hash": entry_hash,
        "prev_hash": prev,
        "cdm_id": cdm_id,
        "maneuver_id": maneuver_id,
        "object": c["primary"]["name"] if c else None,
        "operator": operator,
        "burn_epoch": cand["burn_epoch"],
        "delta_v_mms": cand["delta_v_mms"],
        "direction": cand["direction"],
        "published_at": db.now_iso(),
    })
    return {"published": True, "seq": entry["seq"],
            "entry_hash": entry_hash, "prev_hash": prev}


def _get_ledger():
    entries = db.ledger()
    return {"count": len(entries), "entries": entries}


IMPL = {
    "get_catalog_status": _get_catalog_status,
    "screen_catalog": _screen_catalog,
    "get_conjunctions": _get_conjunctions,
    "assess_conjunction": _assess_conjunction,
    "solve_maneuver": _solve_maneuver,
    "rescreen_trajectory": _rescreen_trajectory,
    "get_plan": _get_plan,
    "publish_intent": _publish_intent,
    "get_ledger": _get_ledger,
}


def dispatch(name, args):
    """Run a tool by name. Errors come back as data, not exceptions -
    the model can read an error and try something else."""
    fn = IMPL.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return fn(**(args or {}))
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def dispatch_for(agent):
    """A dispatch function restricted to one agent's allowed tools."""
    allowed = set(TOOLS.get(agent, []))

    def restricted(name, args):
        if name not in allowed:
            return {"error": f"{agent} is not permitted to call {name}"}
        return dispatch(name, args)
    return restricted


if __name__ == "__main__":
    import json

    print(f"{len(SCHEMAS)} tools defined\n")
    for agent, names in TOOLS.items():
        print(f"  {agent:<12} {', '.join(names)}")

    print("\n--- get_catalog_status ---")
    print(json.dumps(dispatch("get_catalog_status", {}), indent=2))

    print("\n--- get_conjunctions (limit 3) ---")
    out = dispatch("get_conjunctions", {"limit": 3})
    for c in out.get("conjunctions", []):
        print(f"  {c['cdm_id']}  {c['object'][:26]:<26} "
              f"{c['miss_distance_km']:>8.3f} km  "
              f"pc {c['collision_probability']:.2e}  {c['risk']}")

    if out.get("conjunctions"):
        cid = out["conjunctions"][0]["cdm_id"]
        print(f"\n--- assess_conjunction {cid} ---")
        d = dispatch("assess_conjunction", {"cdm_id": cid})
        print(f"  {d['primary']} vs {d['secondary']}")
        print(f"  miss {d['miss_distance_km']} km at "
              f"{d['closing_speed_kms']} km/s, pc {d['collision_probability']:.2e}")
        print(f"  encounter plane: {d['encounter_plane']}")

    print("\n--- permission check ---")
    r = dispatch_for("SCREENER")("publish_intent",
                                 {"cdm_id": "CDM-0001",
                                  "maneuver_id": "MNV-001"})
    print(f"  SCREENER calling publish_intent -> {r}")

    print("\nNot exercised here (slow): screen_catalog, solve_maneuver, "
          "rescreen_trajectory.")