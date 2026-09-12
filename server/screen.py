"""Conjunction screening for Aegis OTM.

Screens one asset against the whole catalog and returns close approaches
ranked by miss distance. Four-stage funnel so the expensive maths only
runs on the handful of pairs that survive.

  1. perigee/apogee filter  - geometric impossibility, kills ~95%
  2. coarse pass (60s)      - keep anything inside COARSE_KM
  3. fine pass (1s)         - re-check a window around each minimum
  4. parabolic fit          - sub-second time of closest approach

Co-orbital objects are excluded. CelesTrak lists ISS modules and docked
vehicles as separate catalog entries sharing the station's TLE, so they
report a zero miss distance. Real conjunction assessment systems exclude
them the same way.

Run directly to self-test:  python screen.py
"""

from datetime import timedelta

import numpy as np

import ingest
import propagate

COARSE_KM = 50.0        # coarse-pass gate
ALT_PAD_KM = 10.0       # slack on the perigee/apogee filter
FINE_WINDOW_S = 180     # +/- seconds around a coarse minimum
CO_ORBITAL_KM = 1e-6    # below this a "conjunction" is the same object

# Objects that share the ISS TLE: station modules plus docked vehicles.
EXCLUDE_NAME_TOKENS = [
    "ISS", "ZARYA", "UNITY", "ZVEZDA", "DESTINY", "NAUKA", "POISK",
    "RASSVET", "PIRS", "QUEST", "HARMONY", "TRANQUILITY", "COLUMBUS",
    "KIBO", "LEONARDO", "BEAM", "CREW DRAGON", "CARGO DRAGON",
    "CYGNUS", "PROGRESS", "SOYUZ", "DRAGON", "STARLINER",
]


def is_co_orbital(name):
    """True if this object shares the station's orbit by construction."""
    n = (name or "").upper()
    return any(tok in n for tok in EXCLUDE_NAME_TOKENS)


# ------------------------------------------------------------------ stage 1

def radial_bounds(r):
    """Min and max geocentric distance each object reaches over the grid.

    Taken from the propagated track rather than derived from the elements:
    one numpy call, and it reflects the span actually screened.
    """
    dist = np.linalg.norm(r, axis=2)          # (n_objects, n_times)
    return dist.min(axis=1), dist.max(axis=1)


def altitude_filter(r, asset_idx, pad_km=ALT_PAD_KM):
    """Indices whose altitude shell could reach the asset's."""
    lo, hi = radial_bounds(r)
    a_lo, a_hi = lo[asset_idx], hi[asset_idx]
    keep = (lo <= a_hi + pad_km) & (hi >= a_lo - pad_km)
    keep[asset_idx] = False
    return np.flatnonzero(keep)


# ------------------------------------------------------------------ stage 2

def coarse_pass(r, asset_idx, candidates, threshold_km=COARSE_KM,
                block_size=2000):
    """Minimum range and its timestep for each candidate.

    Returns (object_index, step_index, range_km) for candidates coming
    within threshold_km at any point on the coarse grid. Chunked because
    the full difference array would be gigabytes.
    """
    asset = r[asset_idx]                       # (n_times, 3)
    hits = []
    for start in range(0, len(candidates), block_size):
        block = candidates[start:start + block_size]
        d = np.linalg.norm(r[block] - asset, axis=2)   # (block, n_times)
        kmin = d.argmin(axis=1)
        dmin = d[np.arange(len(block)), kmin]
        for i in np.flatnonzero(dmin < threshold_km):
            hits.append((int(block[i]), int(kmin[i]), float(dmin[i])))
    return hits


# ------------------------------------------------------------------ stage 3

def fine_pass(sats, asset_idx, obj_idx, coarse_time, window_s=FINE_WINDOW_S):
    """Re-propagate at 1s resolution around a coarse minimum.

    At 14 km/s relative, 60s sampling can miss the true closest approach
    by hundreds of km, so this stage is what turns a coarse hit into a
    real number.

    Returns (times, range_km, (r_asset, v_asset), (r_obj, v_obj)).
    """
    start = coarse_time - timedelta(seconds=window_s)
    jd, fr, times = propagate.time_grid(
        start=start, hours=(2 * window_s) / 3600.0, step_s=1)
    err, r, v = propagate.propagate(sats, jd, fr)
    ra, va = r[asset_idx], v[asset_idx]
    ro, vo = r[obj_idx], v[obj_idx]
    rng = np.linalg.norm(ro - ra, axis=1)
    return times, rng, (ra, va), (ro, vo)


# ------------------------------------------------------------------ stage 4

def refine_tca(times, rng):
    """Parabolic fit through the three points around the minimum.

    A parabola through (-1, y0), (0, y1), (1, y2) has its vertex at
    offset = (y0 - y2) / (2 * (y0 - 2*y1 + y2)) steps from the centre.

    Returns (index, sub_step_offset, fitted_min_range_km).
    """
    k = int(np.argmin(rng))
    y1 = float(rng[k])

    # Degenerate: duplicate TLE or co-orbital. Don't fit a parabola to zeros.
    if y1 < CO_ORBITAL_KM:
        return k, 0.0, 0.0

    if k == 0 or k == len(rng) - 1:
        return k, 0.0, y1

    y0, y2 = float(rng[k - 1]), float(rng[k + 1])
    denom = y0 - 2 * y1 + y2
    if abs(denom) < 1e-12:
        return k, 0.0, y1

    offset = max(-1.0, min(1.0, (y0 - y2) / (2 * denom)))
    fitted = y1 - 0.25 * (y0 - y2) * offset
    return k, offset, float(fitted)


# ------------------------------------------------------- frame decomposition

def rtn_components(r_asset, v_asset, r_other):
    """Miss vector in the asset's RTN frame, in metres.

    R - radial, away from Earth
    T - in-track, along the velocity
    N - cross-track, along the orbit normal

    In-track is usually the largest component, because along-track
    position is the least well-determined part of any orbit.
    """
    R_hat = r_asset / np.linalg.norm(r_asset)
    N_hat = np.cross(r_asset, v_asset)
    N_hat = N_hat / np.linalg.norm(N_hat)
    T_hat = np.cross(N_hat, R_hat)

    d = (r_other - r_asset) * 1000.0           # km -> m
    return {
        "radial": float(np.dot(d, R_hat)),
        "in_track": float(np.dot(d, T_hat)),
        "cross_track": float(np.dot(d, N_hat)),
    }


# ------------------------------------------------------------------ pipeline

def screen_asset(asset_norad=25544, hours=propagate.HORIZON_H,
                 threshold_km=5.0, exclude_co_orbital=True, verbose=True):
    """Full screening run. Returns (conjunctions, asset_metadata)."""
    import time as _t

    cat = ingest.load()
    sats, meta = propagate.build(cat)
    asset_idx = propagate.find(meta, asset_norad)
    if asset_idx is None:
        raise ValueError(f"asset {asset_norad} not in catalog")

    if verbose:
        print(f"asset: {meta[asset_idx]['name']}")

    t0 = _t.time()
    jd, fr, times = propagate.time_grid(hours=hours)
    err, r, v = propagate.propagate(sats, jd, fr)
    if verbose:
        print(f"stage 0  propagated {r.shape[0]} objects "
              f"x {r.shape[1]} steps in {_t.time() - t0:.1f}s")

    cands = altitude_filter(r, asset_idx)
    if verbose:
        pct = 100 * (1 - len(cands) / len(meta))
        print(f"stage 1  altitude filter -> {len(cands)} candidates "
              f"({pct:.1f}% removed)")

    hits = coarse_pass(r, asset_idx, cands)
    n_raw = len(hits)
    if exclude_co_orbital:
        hits = [h for h in hits if not is_co_orbital(meta[h[0]]["name"])]
    if verbose:
        note = ""
        if exclude_co_orbital and n_raw != len(hits):
            note = f" ({n_raw - len(hits)} co-orbital excluded)"
        print(f"stage 2  coarse pass (<{COARSE_KM:.0f} km) "
              f"-> {len(hits)} hits{note}")

    results = []
    for obj_idx, step, coarse_km in hits:
        ftimes, rng, (ra, va), (ro, vo) = fine_pass(
            sats, asset_idx, obj_idx, times[step])
        k, offset, miss_km = refine_tca(ftimes, rng)

        if miss_km < CO_ORBITAL_KM or miss_km > threshold_km:
            continue

        results.append({
            "secondary": meta[obj_idx],
            "tca": ftimes[k] + timedelta(seconds=offset),
            "miss_distance_km": round(miss_km, 4),
            "relative_speed_kms": round(float(np.linalg.norm(vo[k] - va[k])), 3),
            "components_m": rtn_components(ra[k], va[k], ro[k]),
            "coarse_km": round(coarse_km, 3),
        })

    results.sort(key=lambda c: c["miss_distance_km"])
    if verbose:
        print(f"stage 3+ fine pass (<{threshold_km:.0f} km) "
              f"-> {len(results)} conjunctions")
        print(f"total {_t.time() - t0:.1f}s")
    return results, meta[asset_idx]


def report(results):
    print(f"\n{'name':<28} {'miss km':>9} {'rel km/s':>9}  TCA")
    print("-" * 78)
    for c in results[:15]:
        comp = c["components_m"]
        print(f"{c['secondary']['name'][:28]:<28} "
              f"{c['miss_distance_km']:>9.3f} "
              f"{c['relative_speed_kms']:>9.2f}  "
              f"{c['tca'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'':<28} R {comp['radial']:>8.0f}m  "
              f"T {comp['in_track']:>8.0f}m  "
              f"N {comp['cross_track']:>8.0f}m")


if __name__ == "__main__":
    # 24h keeps the self-test quick; the real endpoint uses 72.
    results, asset = screen_asset(hours=24, threshold_km=5.0)
    report(results)

    if not results:
        print("\nNo conjunctions under 5 km - that is the correct answer on")
        print("most days. Re-running at 25 km to confirm the pipeline finds")
        print("real objects...\n")
        results, asset = screen_asset(hours=24, threshold_km=25.0)
        report(results)