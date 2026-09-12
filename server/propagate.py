"""Orbit propagation for Aegis OTM.

Loads the cached CelesTrak catalog, builds a vectorized SGP4 model,
and propagates every object over a time grid.

Run directly to self-test:  python propagate.py
"""

import numpy as np
from datetime import datetime, timedelta, timezone
from sgp4.api import Satrec, SatrecArray, jday
from sgp4 import omm

import ingest

STEP_S = 60
HORIZON_H = 72
EARTH_R = 6378.137          # equatorial radius, km


def classify(name):
    """CelesTrak's GP feed has no OBJECT_TYPE field, so derive it from the
    name. This is the standard naming convention used across the catalog."""
    n = (name or "").upper()
    if "DEB" in n or "FRAGMENT" in n:
        return "DEBRIS"
    if "R/B" in n or "ROCKET BODY" in n:
        return "ROCKET_BODY"
    return "PAYLOAD"


def build(records, verbose=False):
    """Turn cached OMM records into a SatrecArray.

    Returns (SatrecArray, metadata_list). Records that fail to parse are
    dropped; pass verbose=True to see why.
    """
    sats, meta = [], []
    dropped = 0
    first_error = None

    for o in records:
        try:
            f = {k: str(val) for k, val in o.items()}
            # omm.initialize parses EPOCH with a strict %...%S.%f format.
            # CelesTrak omits the fraction when it is exactly zero.
            if "." not in f.get("EPOCH", ""):
                f["EPOCH"] = f.get("EPOCH", "") + ".000000"
            s = Satrec()
            omm.initialize(s, f)
        except Exception as e:
            dropped += 1
            if first_error is None:
                first_error = f"{type(e).__name__}: {e}"
            continue

        sats.append(s)
        name = o.get("OBJECT_NAME", "UNKNOWN")
        meta.append({
            "norad_id": str(o.get("NORAD_CAT_ID", "")),
            "name": name,
            "object_type": classify(name),
            "group": o.get("_group", ""),
            "epoch": o.get("EPOCH"),
        })

    if verbose and dropped:
        print(f"  dropped {dropped} records, first error -> {first_error}")

    return SatrecArray(sats), meta


def time_grid(start=None, hours=HORIZON_H, step_s=STEP_S):
    """Julian date arrays for sgp4.

    sgp4 splits each instant into a whole Julian day (jd) plus a fraction
    (fr) so that sub-second precision survives floating point.

    Returns (jd, fr, datetimes).
    """
    if start is None:
        start = datetime.now(timezone.utc)
    n = int(hours * 3600 / step_s)
    times = [start + timedelta(seconds=k * step_s) for k in range(n)]
    jd = np.empty(n)
    fr = np.empty(n)
    for i, t in enumerate(times):
        a, b = jday(t.year, t.month, t.day, t.hour, t.minute,
                    t.second + t.microsecond * 1e-6)
        jd[i], fr[i] = a, b
    return jd, fr, times


def propagate(sat_array, jd, fr):
    """Positions and velocities for every object at every timestep.

    r is (n_objects, n_times, 3) in km, TEME frame.
    v is (n_objects, n_times, 3) in km/s.
    err is (n_objects, n_times); non-zero means that object failed at
    that timestep (decayed, numerical blow-up, etc).
    """
    err, r, v = sat_array.sgp4(jd, fr)
    return err, r, v


def find(meta, norad_id):
    """Index of an object in the propagated arrays, or None."""
    target = str(norad_id)
    return next((i for i, m in enumerate(meta) if m["norad_id"] == target), None)


def altitude_km(pos_km):
    """Crude altitude from a TEME position vector. Spherical Earth, which
    is fine for sanity checks but not for the geodetic conversion the
    frontend needs."""
    return float(np.linalg.norm(pos_km) - EARTH_R)


if __name__ == "__main__":
    import time

    cat = ingest.load()
    print(f"catalog records : {len(cat)}")

    sats, meta = build(cat, verbose=True)
    print(f"propagable      : {len(meta)}")

    if not meta:
        print("\nNothing propagable. Check the EPOCH / element field names.")
        print("first record keys:", list(cat[0].keys()))
        raise SystemExit(1)

    types = {}
    for m in meta:
        types[m["object_type"]] = types.get(m["object_type"], 0) + 1
    print(f"by type         : {types}")

    jd, fr, times = time_grid(hours=1)
    print(f"timesteps       : {len(jd)} (1 hour @ {STEP_S}s)")

    t0 = time.time()
    err, r, v = propagate(sats, jd, fr)
    print(f"propagated in {time.time() - t0:.2f}s -> shape {r.shape}")
    print(f"erroring at t0  : {int((err[:, 0] != 0).sum())}")

    idx = find(meta, 25544)
    if idx is None:
        print("\nISS (25544) not in catalog - is the 'active' group cached?")
    else:
        pos, vel = r[idx, 0], v[idx, 0]
        print(f"\n{meta[idx]['name']}  (epoch {meta[idx]['epoch']})")
        print(f"  position km : {pos.round(1)}")
        print(f"  velocity    : {np.linalg.norm(vel):.3f} km/s")
        print(f"  altitude    : {altitude_km(pos):.1f} km")
        print("\nSanity check: altitude should be 400-430 km, speed ~7.66 km/s.")
        print("Compare against a live ISS tracker before trusting anything downstream.")