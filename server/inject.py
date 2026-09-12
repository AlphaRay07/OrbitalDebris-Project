"""Synthetic threat injection for Aegis OTM.

The real catalog will not hand you a dangerous conjunction on demand -
genuine sub-kilometre ISS encounters happen a handful of times a year.
This builds one so the demo always has a red event.

The object is clearly labelled SIM-DEBRIS-001 and carries simulated=True
all the way through the API. Disclose it in the demo; a judge who spots
an undisclosed fake will discount everything else you built.

Method: take the asset's own elements, rotate the orbital plane and shift
the phase until the two paths cross at a chosen miss distance. The result
is a physically valid orbit, not a scripted position - it propagates
through SGP4 like any other catalog object.

Two things make the search work where a naive grid does not:

  - Sub-step refinement. At 15 km/s closing speed a 10 s evaluation grid
    resolves the minimum to no better than 75 km, so every candidate is
    re-propagated at 0.05 s around its grid minimum.
  - Geometric refinement. Mean anomaly slides the object along its track
    at roughly 120 km per degree, so a fixed 0.25 deg sweep bottoms out
    around 10 km. Shrinking the step by 4x per level reaches metres.

Run:  python inject.py [target_miss_km]
      python inject.py remove
"""

import copy
import json
import os
import sys

import numpy as np

import ingest
import propagate
import screen

# SGP4 rejects satellite numbers above 339999 (the Alpha-5 ceiling), so
# the synthetic object has to live below that.
SIM_NORAD = "339001"
SIM_NAME = "SIM-DEBRIS-001 (COSMOS 1408 DEB)"
ASSET_NORAD = "25544"

DEFAULT_TARGET_KM = 0.35
SEARCH_HOURS = 48
REFINE_LEVELS = 9

CACHE = os.path.join(os.path.dirname(__file__), "cache")
CATALOG_PATH = os.path.join(CACHE, "catalog.json")


# --------------------------------------------------------------- candidate

def make_candidate(asset_rec, d_inc_deg, d_raan_deg, d_anom_deg,
                   d_mm_rev=0.0):
    """One synthetic object derived from the asset's elements.

    d_mm_rev tunes mean motion, which is the only handle on orbit size.
    It is needed because J2 perturbs orbits of different inclination to
    different actual radii even when their mean semi-major axes match -
    a few km at large inclination offsets, which is otherwise an
    irreducible radial gap between the two paths.
    """
    rec = copy.deepcopy(asset_rec)
    rec["OBJECT_NAME"] = SIM_NAME
    rec["OBJECT_ID"] = "2021-901A"
    rec["NORAD_CAT_ID"] = int(SIM_NORAD)
    rec["_group"] = "simulated"
    rec["_simulated"] = True

    rec["INCLINATION"] = (float(asset_rec["INCLINATION"]) + d_inc_deg) % 180.0
    rec["RA_OF_ASC_NODE"] = (float(asset_rec["RA_OF_ASC_NODE"])
                             + d_raan_deg) % 360.0
    rec["MEAN_ANOMALY"] = (float(asset_rec["MEAN_ANOMALY"])
                           + d_anom_deg) % 360.0
    # Eccentricity and mean motion are left alone deliberately. Two
    # congruent near-circular orbits through the same focus intersect at
    # two points no matter how the planes are oriented, which turns the
    # problem into pure timing that mean anomaly can close. Perturbing
    # the size instead leaves an irreducible radial gap between the two
    # paths - that gap, not the search, is what limits the miss distance.
    #
    # BSTAR is raised so the object decays like a small fragment rather
    # than a station-sized body. Over a two day horizon the effect on
    # position is negligible.
    rec["BSTAR"] = float(asset_rec.get("BSTAR", 0.0)) * 4.0
    rec["MEAN_MOTION"] = float(asset_rec["MEAN_MOTION"]) + d_mm_rev
    return rec


# ----------------------------------------------------------- range helpers

def grid_min(asset_rec, sim_rec, grid):
    """Coarse minimum range over a precomputed grid. Locates the crossing.

    Returns (range_km, time) or (None, None) if the elements were rejected.
    """
    jd, fr, times = grid
    sats, meta = propagate.build([asset_rec, sim_rec])
    if len(meta) < 2:
        return None, None
    err, r, v = propagate.propagate(sats, jd, fr)
    rng = np.linalg.norm(r[1] - r[0], axis=1)
    k = int(np.argmin(rng))
    return float(rng[k]), times[k]


def accurate_min(asset_rec, sim_rec, t_guess, window_s=40, step_s=0.05):
    """True minimum range, by re-propagating densely around a guess.

    Returns (range_km, time, relative_speed_kms).
    """
    from datetime import timedelta
    sats, meta = propagate.build([asset_rec, sim_rec])
    if len(meta) < 2:
        return None, None, None

    start = t_guess - timedelta(seconds=window_s)
    jd, fr, times = propagate.time_grid(
        start=start, hours=(2 * window_s) / 3600.0, step_s=step_s)
    err, r, v = propagate.propagate(sats, jd, fr)
    rng = np.linalg.norm(r[1] - r[0], axis=1)
    k = int(np.argmin(rng))
    rel_v = float(np.linalg.norm(v[1, k] - v[0, k]))
    return float(rng[k]), times[k], rel_v


PARAMS = ("d_anom", "d_raan", "d_inc", "d_mm")

# Per-parameter step scales. Mean motion needs a much smaller absolute
# step than the angles: 0.02 rev/day is already about 6 km of altitude.
STEP_SCALE = {"d_anom": 1.0, "d_raan": 1.0, "d_inc": 1.0, "d_mm": 0.02}


def evaluate(asset_rec, p, coarse_grid, t_centre=None):
    """Accurate miss distance for one parameter set.

    When t_centre is given the minimum is sought near that time rather
    than globally. That matters: a small anomaly change can make some
    other revolution the global minimum, which turns the objective into
    a step function the refinement cannot descend.
    """
    rec = make_candidate(asset_rec, p["d_inc"], p["d_raan"],
                         p["d_anom"], p["d_mm"])
    if t_centre is None:
        coarse_km, t_guess = grid_min(asset_rec, rec, coarse_grid)
        if coarse_km is None:
            return None
    else:
        t_guess = t_centre

    # Wide-ish 1 s pass first, so a shifted crossing is still captured,
    # then the dense sub-second pass.
    mid, t_mid, _ = accurate_min(asset_rec, rec, t_guess,
                                 window_s=2400, step_s=1.0)
    if mid is None:
        return None
    miss, tca, rel_v = accurate_min(asset_rec, rec, t_mid,
                                    window_s=30, step_s=0.02)
    if miss is None:
        return None
    out = dict(p)
    out.update({"miss_km": miss, "tca": tca, "rel_v": rel_v})
    return out


# ----------------------------------------------------------------- search

def search(asset_rec, target_km=DEFAULT_TARGET_KM, verbose=True):
    """Broad sweep for a crossing, then geometric refinement.

    Refinement holds the encounter time fixed to the revolution found by
    the sweep, and tunes four parameters: mean anomaly (arrival timing),
    RAAN and inclination (plane orientation), and mean motion (orbit
    size, which closes the J2 radial gap).
    """
    coarse_grid = propagate.time_grid(hours=SEARCH_HOURS, step_s=60)

    def err(c):
        return abs(c["miss_km"] - target_km)

    # --- stage 1: broad sweep, grid minimum only ---------------------
    best_sweep = None
    for d_inc in (18.0, 26.0, 34.0):
        for d_raan in np.arange(0.0, 360.0, 20.0):
            for d_anom in np.arange(0.0, 360.0, 20.0):
                rec = make_candidate(asset_rec, d_inc, d_raan, d_anom)
                km, t = grid_min(asset_rec, rec, coarse_grid)
                if km is None:
                    continue
                if best_sweep is None or km < best_sweep[0]:
                    best_sweep = (km, t, d_inc, d_raan, d_anom)

    if best_sweep is None:
        probe = make_candidate(asset_rec, 26.0, 40.0, 40.0)
        _, meta = propagate.build([asset_rec, probe], verbose=True)
        print(f"  no candidate propagated ({len(meta)} of 2 element sets built)")
        return None

    _, t_centre, bi, br, ba = best_sweep
    if verbose:
        print(f"  sweep   : {best_sweep[0]:>9.3f} km   "
              f"inc+{bi:.0f} raan+{br:.0f} anom+{ba:.0f}")

    best = evaluate(asset_rec, {"d_inc": bi, "d_raan": br,
                                "d_anom": ba, "d_mm": 0.0},
                    coarse_grid, t_centre=t_centre)
    if best is None:
        return None
    if verbose:
        print(f"  refined : {best['miss_km']:>9.3f} km   "
              f"closing {best['rel_v']:.2f} km/s")

    # --- stage 2: geometric refinement -------------------------------
    step = 2.0
    for level in range(REFINE_LEVELS):
        improved = False
        for param in PARAMS:
            scale = STEP_SCALE[param]
            centre = best[param]
            for delta in (-step, -step / 2, step / 2, step):
                trial = {k: best[k] for k in PARAMS}
                trial[param] = centre + delta * scale
                c = evaluate(asset_rec, trial, coarse_grid,
                             t_centre=t_centre)
                if c and err(c) < err(best):
                    best = c
                    improved = True
        if verbose:
            print(f"  level {level + 1}: {best['miss_km']:>9.3f} km   "
                  f"step {step:.6f}   mm{best['d_mm']:+.5f}")
        if err(best) < target_km * 0.08:
            break
        step /= 4.0 if improved else 2.0

    return best


# ----------------------------------------------------------------- inject

def inject(target_km=DEFAULT_TARGET_KM, verbose=True):
    """Add SIM-DEBRIS-001 to the cached catalog. Idempotent."""
    cat = ingest.load()
    cat = [o for o in cat if str(o.get("NORAD_CAT_ID")) != SIM_NORAD]

    asset = next((o for o in cat
                  if str(o.get("NORAD_CAT_ID")) == ASSET_NORAD), None)
    if asset is None:
        raise SystemExit(f"asset {ASSET_NORAD} not in catalog")

    if screen.is_co_orbital(SIM_NAME):
        raise SystemExit("SIM_NAME matches a co-orbital exclusion token "
                         "and would be filtered out. Rename it.")

    if verbose:
        print(f"searching for a {target_km} km crossing with "
              f"{asset['OBJECT_NAME']}\n")

    best = search(asset, target_km=target_km, verbose=verbose)
    if best is None:
        raise SystemExit("search failed")

    rec = make_candidate(asset, best["d_inc"], best["d_raan"],
                         best["d_anom"], best["d_mm"])
    cat.append(rec)
    os.makedirs(CACHE, exist_ok=True)
    with open(CATALOG_PATH, "w") as f:
        json.dump(cat, f)

    if verbose:
        print(f"\ninjected {SIM_NAME}")
        print(f"  norad       : {SIM_NORAD}")
        print(f"  miss        : {best['miss_km'] * 1000:.0f} m")
        print(f"  closing     : {best['rel_v']:.2f} km/s")
        print(f"  tca         : {best['tca'].strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"  inclination : {rec['INCLINATION']:.2f} deg "
              f"(asset {float(asset['INCLINATION']):.2f})")
        print(f"  mean motion : {rec['MEAN_MOTION']:.6f} rev/day "
              f"(asset {float(asset['MEAN_MOTION']):.6f})")
        print(f"  catalog     : {len(cat)} objects")
        print("\nRe-run the screening to pick it up:")
        print("  python runner.py 72 50")
    return rec, best


def remove(verbose=True):
    """Take the synthetic object back out of the catalog."""
    cat = ingest.load()
    before = len(cat)
    cat = [o for o in cat if str(o.get("NORAD_CAT_ID")) != SIM_NORAD]
    with open(CATALOG_PATH, "w") as f:
        json.dump(cat, f)
    if verbose:
        print(f"removed {before - len(cat)} object(s), {len(cat)} remain")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "remove":
        remove()
    else:
        target = float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TARGET_KM
        inject(target_km=target)