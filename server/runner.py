"""Screening runner for Aegis OTM.

Ties screen.py, probability.py and geodetic.py together and produces
records in exactly the shape CONTRACT.md promises. The endpoints in
app.py call into here; they never touch the physics modules directly.

Run directly to do a full screening pass and print what the API sees:
    python runner.py
"""

import time as _t

import numpy as np

import db
import geodetic
import ingest
import probability
import propagate
import screen

DEFAULT_ASSET = 25544        # ISS
EPHEMERIS_STEP_S = 60

# Crewed vehicles and active payloads can manoeuvre; debris cannot.
MANEUVERABLE_TYPES = {"PAYLOAD"}


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def object_payload(meta, tle_age_h=None):
    """The Object shape from the contract."""
    otype = meta.get("object_type", "UNKNOWN")
    return {
        "norad_id": meta.get("norad_id"),
        "name": meta.get("name", "UNKNOWN"),
        "object_type": otype,
        "size_class": meta.get("rcs_size") or "UNKNOWN",
        "maneuverable": otype in MANEUVERABLE_TYPES,
        "operator": None,
        "tle_age_hours": tle_age_h,
    }


def run(asset_norad=DEFAULT_ASSET, hours=propagate.HORIZON_H,
        threshold_km=5.0, verbose=True):
    """Full screening pass. Writes results to db and returns the summary."""
    t0 = _t.time()
    db.set_state("running", 0.05)

    cat = ingest.load()
    sats, meta = propagate.build(cat)
    asset_idx = propagate.find(meta, asset_norad)
    if asset_idx is None:
        db.set_state("error", 0.0)
        raise ValueError(f"asset {asset_norad} not in catalog")

    db.set_state("running", 0.15)

    results, asset_meta = screen.screen_asset(
        asset_norad=asset_norad, hours=hours,
        threshold_km=threshold_km, verbose=verbose)

    db.set_state("running", 0.7)

    # Re-propagate on the coarse grid once. We need states at TCA for the
    # covariance rotation, and tracks for the ephemeris endpoint.
    jd, fr, times = propagate.time_grid(hours=hours, step_s=EPHEMERIS_STEP_S)
    err, r, v = propagate.propagate(sats, jd, fr)

    asset_age = probability.epoch_age_hours(asset_meta.get("epoch"))
    primary = object_payload(asset_meta, round(asset_age, 1))
    primary["maneuverable"] = True          # the asset is ours

    conjunctions = []
    for c in results:
        sec_meta = c["secondary"]
        obj_idx = propagate.find(meta, sec_meta["norad_id"])
        if obj_idx is None:
            continue

        # Nearest coarse step to TCA, for the state vectors.
        tca = c["tca"]
        k = int(min(range(len(times)),
                    key=lambda i: abs((times[i] - tca).total_seconds())))

        # Time from now to TCA. Drives most of the covariance growth at a
        # 72 hour horizon, so a conjunction three days out is genuinely
        # more uncertain than one three hours out.
        lead_h = max(0.0, (tca - times[0]).total_seconds() / 3600.0)

        assess = probability.assess(
            r[asset_idx, k], v[asset_idx, k],
            r[obj_idx, k], v[obj_idx, k],
            asset_meta, sec_meta, lead_hours=lead_h)

        sec_age = assess["tle_age_hours"]["secondary"]

        conjunctions.append({
            "id": None,
            "primary": primary,
            "secondary": object_payload(sec_meta, sec_age),
            "tca": iso(tca),
            "miss_distance_km": c["miss_distance_km"],
            "relative_speed_kms": c["relative_speed_kms"],
            "pc": assess["pc"],
            "risk": assess["risk"],
            "status": "TRIAGED",
            "simulated": bool(sec_meta.get("simulated")),
            # detail-only fields
            "components_m": {k2: round(val, 1)
                             for k2, val in c["components_m"].items()},
            "encounter_plane": {
                "miss_x_m": assess["miss_x_m"],
                "miss_y_m": assess["miss_y_m"],
                "sigma_major_m": assess["sigma_major_m"],
                "sigma_minor_m": assess["sigma_minor_m"],
                "rotation_deg": assess["rotation_deg"],
                "hbr_m": assess["hbr_m"],
                "pc": assess["pc"],
            },
            "lead_hours": round(lead_h, 1),
            "_asset_idx": asset_idx,
            "_obj_idx": obj_idx,
            "_tca_index": k,
        })

    # Rank by risk, then by probability descending, then miss distance.
    # IDs are assigned after sorting so CDM-0001 is always the top threat.
    rank = {"RED": 0, "AMBER": 1, "GREEN": 2}
    conjunctions.sort(key=lambda c: (rank.get(c["risk"], 9),
                                     -c["pc"],
                                     c["miss_distance_km"]))
    for n, c in enumerate(conjunctions, start=1):
        c["id"] = f"CDM-{n:04d}"

    runtime = round(_t.time() - t0, 1)
    screening = {
        "state": "complete",
        "progress": 1.0,
        "asset_id": str(asset_norad),
        "horizon_hours": hours,
        "threshold_km": threshold_km,
        "pairs_screened": len(meta) - 1,
        "runtime_s": runtime,
        "completed_at": db.now_iso(),
    }

    db.put_screening(screening, primary, conjunctions,
                     probability.assumptions())

    if verbose:
        print(f"\nstored {len(conjunctions)} conjunctions in {runtime}s")
    return screening


def ephemeris(cdm_id, hours=propagate.HORIZON_H):
    """Lat/lon/alt tracks for both objects in a conjunction.

    Re-propagates rather than caching 800 KB of track per conjunction.
    """
    c = db.conjunction(cdm_id)
    if c is None:
        return None

    # Build a Satrec for the two objects only. Rebuilding all 19k just to
    # propagate two of them costs several seconds per request.
    cat = ingest.load()
    want = {c["primary"]["norad_id"], c["secondary"]["norad_id"]}
    subset = [o for o in cat if str(o.get("NORAD_CAT_ID")) in want]
    if len(subset) < 2:
        return None

    sats, meta = propagate.build(subset)
    a_idx = propagate.find(meta, c["primary"]["norad_id"])
    b_idx = propagate.find(meta, c["secondary"]["norad_id"])
    if a_idx is None or b_idx is None:
        return None

    jd, fr, times = propagate.time_grid(hours=hours, step_s=EPHEMERIS_STEP_S)
    err, r, v = propagate.propagate(sats, jd, fr)

    return {
        "cdm_id": cdm_id,
        "tca": c["tca"],
        "tca_index": c.get("_tca_index", 0),
        "step_seconds": EPHEMERIS_STEP_S,
        "epochs": [iso(t) for t in times],
        "tracks": [
            {"object_id": c["primary"]["norad_id"],
             "name": c["primary"]["name"],
             "role": "primary",
             "track": geodetic.track(r[a_idx], jd, fr)},
            {"object_id": c["secondary"]["norad_id"],
             "name": c["secondary"]["name"],
             "role": "secondary",
             "track": geodetic.track(r[b_idx], jd, fr)},
        ],
    }


def debris_cloud(n=300, hours=1):
    """Static scatter for the globe backdrop. Capped for framerate."""
    cat = ingest.load()
    sats, meta = propagate.build(cat)
    idx = [i for i, m in enumerate(meta) if m["object_type"] == "DEBRIS"]
    if not idx:
        return {"count": 0, "points": []}
    step = max(1, len(idx) // n)
    idx = idx[::step][:n]

    jd, fr, times = propagate.time_grid(hours=hours, step_s=3600)
    err, r, v = propagate.propagate(sats, jd, fr)

    lat, lon, alt = geodetic.to_geodetic_fast(r[idx, 0], jd[:1] * len(idx),
                                              fr[:1] * len(idx))
    pts = [{"lat": round(float(a), 2), "lon": round(float(b), 2),
            "alt_km": round(float(cc), 1)}
           for a, b, cc in zip(lat, lon, alt)]
    return {"count": len(pts), "points": pts}


def density(shell_km=25):
    """Object count per altitude shell, for the histogram."""
    cat = ingest.load()
    sats, meta = propagate.build(cat)
    jd, fr, times = propagate.time_grid(hours=1, step_s=3600)
    err, r, v = propagate.propagate(sats, jd, fr)

    alt = np.linalg.norm(r[:, 0, :], axis=1) - geodetic.A_EARTH
    alt = alt[(alt > 200) & (alt < 2000)]

    edges = np.arange(200, 2000 + shell_km, shell_km)
    counts, _ = np.histogram(alt, bins=edges)

    return {
        "shell_km": shell_km,
        "shells": [
            {"alt_min_km": int(edges[i]), "alt_max_km": int(edges[i + 1]),
             "object_count": int(counts[i]), "conjunction_count": 0}
            for i in range(len(counts)) if counts[i] > 0
        ],
    }


if __name__ == "__main__":
    import sys

    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    thresh = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0

    print(f"screening {hours}h at {thresh} km\n")
    summary = run(hours=hours, threshold_km=thresh)

    print(f"\nstate    : {summary['state']}")
    print(f"runtime  : {summary['runtime_s']}s")
    print(f"screened : {summary['pairs_screened']} objects")
    print(f"counts   : {db.risk_counts()}")

    print("\nwhat GET /api/conjunctions returns:")
    print(f"  {'id':<10} {'object':<26} {'miss km':>9} {'pc':>10}  risk")
    for c in db.conjunction_list():
        print(f"  {c['id']:<10} {c['secondary']['name'][:26]:<26} "
              f"{c['miss_distance_km']:>9.3f} {c['pc']:>10.2e}  {c['risk']}")

    lst = db.conjunction_list()
    if lst:
        cid = lst[0]["id"]
        d = db.conjunction(cid)
        print(f"\nwhat GET /api/conjunctions/{cid} adds:")
        print(f"  components_m    : {d['components_m']}")
        print(f"  encounter_plane : {d['encounter_plane']}")

        print(f"\nbuilding ephemeris for {cid}...")
        t0 = _t.time()
        eph = ephemeris(cid, hours=hours)
        print(f"  {len(eph['epochs'])} epochs, "
              f"{len(eph['tracks'])} tracks in {_t.time() - t0:.1f}s")
        print(f"  first primary point: {eph['tracks'][0]['track'][0]}")
        print(f"  tca_index: {eph['tca_index']}")
    else:
        print("\nno conjunctions stored - raise the threshold")