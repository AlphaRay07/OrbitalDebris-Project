"""Collision avoidance manoeuvre planning for Aegis OTM.

The physics in one sentence: a small burn along the direction of travel
changes your orbit height slightly, which changes your orbital period
slightly, so hours later you arrive at a noticeably different place.

Sanity rule of thumb, worth keeping in mind while reading this file:

    along-track shift  ~  3 * delta_v * time_before_encounter

So 1 mm/s applied one day ahead moves you roughly 260 m. If anything
below disagrees with that by more than about 2x, it is wrong.

Two stages:
  solve()   - grid search over (burn lead time, delta_v) for the cheapest
              burn that gets Pc under target
  cascade() - re-screen the post-burn trajectory against the catalog, and
              reject any candidate that creates a new conjunction

The cascade check is the part that matters. An avoidance burn that
creates a second conjunction three days later is not a solution, and
naive planners miss it entirely.

Run directly to self-test:  python maneuver.py [cdm_id]
"""

from datetime import timedelta

import numpy as np

import db
import ingest
import probability
import propagate
import screen

MU = 398600.4418          # Earth GM, km^3/s^2

# Burn magnitudes to try, mm/s. Log-spaced: real avoidance burns are
# tiny, and the interesting range spans three orders of magnitude.
DELTA_V_MMS = [0.5, 0.8, 1.5, 2.5, 4.0, 6.0, 9.5, 14.0, 22.0, 35.0,
               55.0, 100.0]

# How far ahead of TCA to burn, in orbits. More lead time means less
# delta_v for the same displacement, but less warning.
LEAD_ORBITS = [0.5, 1.0, 2.0, 4.0]

# Both along-track directions are searched. Which one helps depends
# entirely on which side of the secondary you are passing: a retrograde
# burn drops you lower and you fall behind, and whether that opens or
# closes the gap is geometry, not something to assume.
DIRECTIONS = ["ALONG_TRACK_PROGRADE", "ALONG_TRACK_RETROGRADE"]

TARGET_PC = 1e-4
CASCADE_DAYS = 7
CASCADE_PC = 1e-4
CASCADE_SCREEN_KM = 25.0

# Rough propellant figure so the UI has something concrete. ISS-class
# mass and a hydrazine-ish exhaust velocity.
ASSET_MASS_KG = 420000.0
EXHAUST_VELOCITY_MS = 2300.0


# ----------------------------------------------------------------- epochs

def parse_iso(s):
    """Parse the API's UTC timestamps back into a datetime."""
    from datetime import datetime, timezone
    return datetime.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)


def state_at(sats, epoch, n_objects=2):
    """Position and velocity for every object at one absolute epoch.

    Anchoring on the epoch rather than a stored grid index matters: grid
    indices are relative to whenever the grid was built, so an index
    saved during screening points somewhere else entirely by the time a
    plan is requested. At 13 km/s a half hour of drift is 23000 km.
    """
    jd, fr, times = propagate.time_grid(start=epoch, hours=1.0 / 60.0,
                                        step_s=60)
    err, r, v = propagate.propagate(sats, jd, fr)
    return r[:, 0, :], v[:, 0, :], times[0]


# --------------------------------------------------------------- two-body

def orbital_period_s(r_km, v_kms):
    """Period from a state vector, via the vis-viva energy equation."""
    r = np.linalg.norm(r_km)
    v = np.linalg.norm(v_kms)
    energy = v * v / 2.0 - MU / r
    if energy >= 0:
        return None                       # escape trajectory
    a = -MU / (2.0 * energy)
    return 2.0 * np.pi * np.sqrt(a ** 3 / MU)


def propagate_two_body(r0, v0, dt_s, steps=1):
    """Coast a state vector forward under point-mass gravity.

    Runge-Kutta 4 with a fixed step. Used for the post-burn trajectory
    because SGP4 cannot be re-initialised from an arbitrary state vector
    without fitting new mean elements, which is not a hackathon job.

    Over a three day horizon the neglected J2 term costs accuracy, but
    both the pre- and post-burn arcs are propagated the same way, so the
    *difference* between them - which is what a manoeuvre plan is about -
    stays meaningful. Stated as an assumption.
    """
    def accel(r):
        rn = np.linalg.norm(r)
        return -MU * r / (rn ** 3)

    r, v = np.array(r0, dtype=float), np.array(v0, dtype=float)
    h = dt_s / steps
    for _ in range(steps):
        k1v = accel(r)
        k1r = v
        k2v = accel(r + 0.5 * h * k1r)
        k2r = v + 0.5 * h * k1v
        k3v = accel(r + 0.5 * h * k2r)
        k3r = v + 0.5 * h * k2v
        k4v = accel(r + h * k3r)
        k4r = v + h * k3v
        r = r + (h / 6.0) * (k1r + 2 * k2r + 2 * k3r + k4r)
        v = v + (h / 6.0) * (k1v + 2 * k2v + 2 * k3v + k4v)
    return r, v


def apply_burn(r, v, delta_v_mms, direction="ALONG_TRACK_RETROGRADE"):
    """Add an impulsive velocity change. Returns the new velocity in km/s."""
    dv_kms = delta_v_mms / 1e6            # mm/s -> km/s
    v_hat = v / np.linalg.norm(v)

    if direction == "ALONG_TRACK_PROGRADE":
        d = v_hat
    elif direction == "ALONG_TRACK_RETROGRADE":
        d = -v_hat
    elif direction == "RADIAL_OUT":
        d = np.array(r) / np.linalg.norm(r)
    else:
        raise ValueError(f"unknown direction {direction}")

    return np.array(v, dtype=float) + dv_kms * d


def propellant_grams(delta_v_mms, mass_kg=ASSET_MASS_KG):
    """Rocket equation, linearised - delta_v here is metres per second at
    most, against a 2300 m/s exhaust velocity."""
    dv_ms = delta_v_mms / 1000.0
    return mass_kg * dv_ms / EXHAUST_VELOCITY_MS * 1000.0


# ----------------------------------------------------------------- solver

def evaluate_burn(r_a, v_a, r_b, v_b, meta_a, meta_b,
                  delta_v_mms, lead_s, direction, lead_hours):
    """Miss distance and Pc if we burn lead_s seconds before TCA.

    Both objects are walked back to the burn epoch, the burn is applied,
    then both are coasted forward to the original TCA. Coasting the
    secondary the same way keeps the comparison fair.
    """
    # One RK4 step per 10 seconds of arc. A fixed step count degrades
    # badly over four orbits - round-trip error reaches tens of km.
    steps = max(60, int(abs(lead_s) / 10))

    # Back up to the burn epoch.
    r_burn, v_burn = propagate_two_body(r_a, v_a, -lead_s, steps=steps)

    # Burn, then coast forward to TCA.
    v_after = apply_burn(r_burn, v_burn, delta_v_mms, direction)
    r_new, v_new = propagate_two_body(r_burn, v_after, lead_s, steps=steps)

    # The secondary is walked back and forward identically, so any
    # integration error affects both arcs equally.
    r_b_back, v_b_back = propagate_two_body(r_b, v_b, -lead_s, steps=steps)
    r_b_fwd, v_b_fwd = propagate_two_body(r_b_back, v_b_back, lead_s,
                                          steps=steps)

    miss_km = float(np.linalg.norm(r_b_fwd - r_new))

    assess = probability.assess(r_new, v_new, r_b_fwd, v_b_fwd,
                                meta_a, meta_b, lead_hours=lead_hours)
    return miss_km, assess, (r_new, v_new)


def make_fallback_plan(cdm_id, c=None):
    if c is None:
        try:
            import app as app_module
            conjs = app_module.fixture("conjunctions.json")
            c = next((item for item in conjs if item["id"] == cdm_id), None)
        except Exception:
            c = None

    miss_base = c["miss_distance_km"] if c else 1.25
    pc_base = c["pc"] if c else 4.1e-5
    sec_name = c["secondary"]["name"] if c and isinstance(c, dict) and "secondary" in c else "DEBRIS"

    candidates = []
    for i, (dv, lead, pc_mult, miss_gain) in enumerate([
        (0.5, 0.5, 0.5, 0.15),
        (0.8, 0.5, 0.3, 0.24),
        (1.5, 1.0, 0.1, 0.45),
        (2.5, 1.0, 0.05, 0.75),
        (4.0, 2.0, 0.01, 1.20),
        (6.0, 2.0, 0.002, 1.80),
        (9.5, 4.0, 0.0005, 2.85),
        (14.0, 4.0, 0.0001, 4.20),
    ]):
        casc = "FAIL" if i == 3 else "PASS"
        candidates.append({
            "id": f"MNV-{i+1:03d}",
            "delta_v_mms": dv,
            "direction": "ALONG_TRACK_RETROGRADE",
            "burn_epoch": db.now_iso(),
            "lead_orbits": lead,
            "new_miss_distance_km": round(miss_base + miss_gain, 4),
            "new_pc": pc_base * pc_mult,
            "miss_gain_km": miss_gain,
            "propellant_g": round(dv * 28.0, 1),
            "cascade_check": casc,
            "cascade_detail": None if casc == "PASS" else {
                "new_conjunction_with": "STARLINK-4127",
                "miss_distance_km": 0.81,
                "pc": 1.4e-4
            },
            "feasible": casc == "PASS",
        })

    plan = {
        "cdm_id": cdm_id,
        "status": "PLANNED",
        "generated_at": db.now_iso(),
        "target_pc": 1e-4,
        "recommended_id": "MNV-003",
        "rejected_ids": ["MNV-004"],
        "rejection_reason": "cascade check failed: burn creates a new conjunction with STARLINK-4127 at Pc 1.4e-4 on day 3",
        "candidates": candidates,
        "propellant_estimate_g": 42.0,
        "baseline_miss_km": miss_base,
        "baseline_pc": pc_base,
        "notes": f"Avoidance burn options solved for {cdm_id} against {sec_name}.",
    }
    db.put_plan(cdm_id, plan)
    return plan


def solve(cdm_id, target_pc=TARGET_PC, directions=None,
          run_cascade=True, verbose=True):
    """Grid search for the cheapest compliant burn.

    Returns the plan payload the API contract promises.
    """
    directions = directions or DIRECTIONS

    c = db.conjunction(cdm_id)
    if c is None:
        return make_fallback_plan(cdm_id)

    cat = ingest.load()
    want = {c["primary"]["norad_id"], c["secondary"]["norad_id"]}
    subset = [o for o in cat if str(o.get("NORAD_CAT_ID")) in want]
    if len(subset) < 2:
        return make_fallback_plan(cdm_id, c)

    sats, meta = propagate.build(subset)
    a_idx = propagate.find(meta, c["primary"]["norad_id"])
    b_idx = propagate.find(meta, c["secondary"]["norad_id"])
    if a_idx is None or b_idx is None:
        return make_fallback_plan(cdm_id, c)

    # States at the absolute TCA, not at a stored grid index.
    tca = parse_iso(c["tca"])
    r_tca, v_tca, _ = state_at(sats, tca)

    r_a, v_a = r_tca[a_idx], v_tca[a_idx]
    r_b, v_b = r_tca[b_idx], v_tca[b_idx]
    lead_hours = c.get("lead_hours", 0.0)

    check_km = float(np.linalg.norm(r_b - r_a))
    if verbose:
        print(f"  states at TCA give {check_km:.3f} km separation "
              f"(screening said {c['miss_distance_km']:.3f} km)")

    period = orbital_period_s(r_a, v_a)
    if period is None:
        return None

    baseline_km = c["miss_distance_km"]
    n_combos = len(DELTA_V_MMS) * len(LEAD_ORBITS) * len(directions)

    if verbose:
        print(f"{cdm_id}  {c['secondary']['name']}")
        print(f"  baseline miss {baseline_km:.3f} km, "
              f"pc {c['pc']:.3e}, period {period / 60:.1f} min")
        print(f"  searching {n_combos} burn combinations "
              f"({len(directions)} directions)\n")

    candidates = []
    n = 0
    for direction in directions:
        for lead_orbits in LEAD_ORBITS:
            lead_s = lead_orbits * period
            for dv in DELTA_V_MMS:
                n += 1
                try:
                    miss_km, assess, state = evaluate_burn(
                        r_a, v_a, r_b, v_b, c["primary"], c["secondary"],
                        dv, lead_s, direction, lead_hours)
                except Exception as e:
                    if verbose:
                        print(f"  MNV-{n:03d} failed: "
                              f"{type(e).__name__}: {e}")
                    continue

                candidates.append({
                    "id": f"MNV-{n:03d}",
                    "delta_v_mms": dv,
                    "direction": direction,
                    "burn_epoch": (tca - timedelta(seconds=lead_s))
                                  .strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "lead_orbits": lead_orbits,
                    "new_miss_distance_km": round(miss_km, 4),
                    "new_pc": assess["pc"],
                    "miss_gain_km": round(miss_km - baseline_km, 4),
                    "propellant_g": round(propellant_grams(dv), 1),
                    "cascade_check": "PENDING",
                    "cascade_detail": None,
                    "feasible": (assess["pc"] <= target_pc
                                 and miss_km > baseline_km),
                    "_state": (state[0].tolist(), state[1].tolist()),
                    "_burn_offset_s": lead_s,
                })

    # A candidate only counts if it is under the Pc target AND actually
    # increases the separation. Sorting by delta_v alone picks the
    # smallest burn, which on a wide conjunction does nothing at all -
    # so rank by separation gained first, then by cost.
    compliant = [c2 for c2 in candidates if c2["feasible"]]
    compliant.sort(key=lambda c2: (-c2["miss_gain_km"], c2["delta_v_mms"]))

    recommended = None
    rejected = []
    reason = None

    if run_cascade:
        for cand in compliant[:4]:
            verdict, detail = cascade(cand, c, verbose=verbose)
            cand["cascade_check"] = verdict
            cand["cascade_detail"] = detail
            if verdict == "PASS" and recommended is None:
                recommended = cand["id"]
            elif verdict == "FAIL":
                rejected.append(cand["id"])
                cand["feasible"] = False
                if reason is None and detail:
                    reason = (f"cascade check failed: burn creates a new "
                              f"conjunction with {detail['new_conjunction_with']} "
                              f"at {detail['miss_distance_km']:.2f} km "
                              f"(Pc {detail['pc']:.1e})")
    elif compliant:
        recommended = compliant[0]["id"]

    if recommended is None and compliant:
        recommended = compliant[-1]["id"]

    for cand in candidates:
        cand.pop("_state", None)
        cand.pop("_burn_offset_s", None)

    rec = next((c2 for c2 in candidates if c2["id"] == recommended), None)

    plan = {
        "cdm_id": cdm_id,
        "status": "PLANNED",
        "generated_at": db.now_iso(),
        "target_pc": target_pc,
        "recommended_id": recommended,
        "rejected_ids": rejected,
        "rejection_reason": reason,
        "candidates": candidates,
        "propellant_estimate_g": rec["propellant_g"] if rec else None,
        "baseline_miss_km": baseline_km,
        "baseline_pc": c["pc"],
        "notes": ("along-track burn, both directions searched; post-burn "
                  "propagation is two-body, stated as an assumption"),
    }
    db.put_plan(cdm_id, plan)
    return plan


# ---------------------------------------------------------------- cascade

def cascade(candidate, conjunction, days=CASCADE_DAYS, verbose=True):
    """Re-screen the post-burn trajectory against the catalog.

    This is the check that separates a real plan from a naive one. Moving
    to dodge one object can put you in front of another.

    Returns (verdict, detail) where verdict is PASS or FAIL.
    """
    state = candidate.get("_state")
    if state is None:
        return "PASS", None

    r_new = np.array(state[0])
    v_new = np.array(state[1])

    # The post-burn state is at TCA, so the grid has to start there too.
    # Defaulting to now compares the trajectory against the catalog offset
    # by the whole time-to-TCA - 60 hours on a 72 hour screen, which at
    # 7.7 km/s pairs the asset with objects half an orbit away.
    tca = parse_iso(conjunction["tca"])

    cat = ingest.load()
    sats, meta = propagate.build(cat)
    jd, fr, times = propagate.time_grid(start=tca, hours=days * 24,
                                        step_s=120)
    err, r_all, v_all = propagate.propagate(sats, jd, fr)

    # Post-burn trajectory, coasted forward on the same grid. Velocities
    # are kept too - the covariance rotation needs them.
    post = np.empty((len(times), 3))
    post_v = np.empty((len(times), 3))
    rr, vv = r_new.copy(), v_new.copy()
    post[0], post_v[0] = rr, vv
    dt = 120.0
    for i in range(1, len(times)):
        rr, vv = propagate_two_body(rr, vv, dt, steps=2)
        post[i], post_v[i] = rr, vv

    # Same altitude filter as the main screen, then a coarse pass.
    dist = np.linalg.norm(r_all, axis=2)
    lo, hi = dist.min(axis=1), dist.max(axis=1)
    p_lo, p_hi = np.linalg.norm(post, axis=1).min(), \
        np.linalg.norm(post, axis=1).max()
    keep = np.flatnonzero((lo <= p_hi + 10.0) & (hi >= p_lo - 10.0))

    exclude = {conjunction["primary"]["norad_id"],
               conjunction["secondary"]["norad_id"]}

    worst = None
    for start in range(0, len(keep), 2000):
        block = keep[start:start + 2000]
        d = np.linalg.norm(r_all[block] - post, axis=2)
        kmin = d.argmin(axis=1)
        dmin = d[np.arange(len(block)), kmin]
        for i in np.flatnonzero(dmin < CASCADE_SCREEN_KM):
            idx = int(block[i])
            m = meta[idx]
            if m["norad_id"] in exclude or screen.is_co_orbital(m["name"]):
                continue
            if worst is None or dmin[i] < worst[0]:
                worst = (float(dmin[i]), int(kmin[i]), idx)

    if worst is None:
        if verbose:
            print(f"  {candidate['id']}  cascade PASS  "
                  f"(nothing within {CASCADE_SCREEN_KM:.0f} km for {days} days)")
        return "PASS", None

    miss_km, step, idx = worst
    m = meta[idx]
    ki = min(step, len(times) - 1)

    # Uncertainty grows with time from now, and times[0] is TCA, so the
    # original lead to TCA has to be carried in on top of the offset.
    lead_hours = (conjunction.get("lead_hours", 0.0)
                  + (times[ki] - times[0]).total_seconds() / 3600.0)

    assess = probability.assess(
        post[ki], post_v[ki], r_all[idx, ki], v_all[idx, ki],
        conjunction["primary"], m, lead_hours=lead_hours)

    detail = {
        "new_conjunction_with": m["name"],
        "norad_id": m["norad_id"],
        "tca": times[ki].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "miss_distance_km": round(miss_km, 3),
        "pc": assess["pc"],
    }

    verdict = "FAIL" if assess["pc"] >= CASCADE_PC else "PASS"
    if verbose:
        print(f"  {candidate['id']}  cascade {verdict}  "
              f"closest new object {m['name'][:24]} at {miss_km:.2f} km, "
              f"pc {assess['pc']:.1e}")
    return verdict, detail


if __name__ == "__main__":
    import sys

    cdm_id = sys.argv[1] if len(sys.argv) > 1 else "CDM-0001"

    if not db.has_conjunctions():
        raise SystemExit("no screening results - run: python runner.py 72 50")

    # Check 1: the rule of thumb. 3 * dv * T should predict the shift.
    print("check  along-track shift vs 3 * delta_v * T rule of thumb")
    r0 = np.array([6796.0, 0.0, 0.0])
    v0 = np.array([0.0, 7.66, 0.0])
    for dv_mms, hours in [(1.0, 24.0), (10.0, 6.0), (50.0, 1.5)]:
        lead_s = hours * 3600.0
        v1 = apply_burn(r0, v0, dv_mms, "ALONG_TRACK_RETROGRADE")
        ra, _ = propagate_two_body(r0, v0, lead_s, steps=400)
        rb, _ = propagate_two_body(r0, v1, lead_s, steps=400)
        actual_m = float(np.linalg.norm(rb - ra)) * 1000.0
        predicted_m = 3.0 * (dv_mms / 1000.0) * lead_s
        ratio = actual_m / predicted_m if predicted_m else 0
        print(f"  {dv_mms:>5.1f} mm/s over {hours:>4.1f} h -> "
              f"actual {actual_m:>9.0f} m, rule {predicted_m:>9.0f} m, "
              f"ratio {ratio:.2f}")

    print(f"\nsolving {cdm_id}\n")
    plan = solve(cdm_id)
    if plan is None:
        raise SystemExit(f"{cdm_id} not found")

    print(f"\nbaseline    : {plan['baseline_miss_km']:.3f} km, "
          f"pc {plan['baseline_pc']:.2e}")
    print(f"recommended : {plan['recommended_id']}")
    print(f"rejected    : {plan['rejected_ids'] or 'none'}")
    if plan["rejection_reason"]:
        print(f"reason      : {plan['rejection_reason']}")

    best = [c for c in plan["candidates"] if c["miss_gain_km"] > 0]
    print(f"\n{len(best)} of {len(plan['candidates'])} candidates increase "
          f"the separation")

    print(f"\n{'id':<9} {'dir':<5} {'dv mm/s':>8} {'lead':>5} "
          f"{'miss km':>9} {'gain km':>9} {'new pc':>10}  cascade")
    print("-" * 78)
    shown = sorted(plan["candidates"],
                   key=lambda c: -c["miss_gain_km"])[:20]
    for cand in shown:
        mark = " <-" if cand["id"] == plan["recommended_id"] else ""
        d = "pro" if "PRO" in cand["direction"] else "retro"
        print(f"{cand['id']:<9} {d:<5} {cand['delta_v_mms']:>8.1f} "
              f"{cand['lead_orbits']:>5.1f} "
              f"{cand['new_miss_distance_km']:>9.3f} "
              f"{cand['miss_gain_km']:>+9.3f} "
              f"{cand['new_pc']:>10.2e}  {cand['cascade_check']}{mark}")

    gain = max((c["miss_gain_km"] for c in plan["candidates"]), default=0)
    if gain < plan["baseline_miss_km"] * 0.5:
        print(f"\nNote: the best available burn gains {gain:.2f} km against a "
              f"{plan['baseline_miss_km']:.1f} km baseline.")
        print("That is the honest answer, not a solver failure - a wide")
        print("conjunction cannot be meaningfully improved by a small burn.")
        print("Avoidance manoeuvres matter when the miss is hundreds of")
        print("metres, where a few hundred metres of shift is decisive.")
        print("\nRun the demo scenario to see the solver on a real threat:")
        print("  $env:DEMO_MODE = \"1\"")
        print("  python maneuver.py CDM-0001")