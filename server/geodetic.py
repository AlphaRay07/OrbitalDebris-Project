"""TEME to geodetic conversion.

The API contract promises orbit tracks as [lat_deg, lon_deg, alt_km].
SGP4 gives us TEME - an Earth-centred inertial frame that does not rotate
with the planet - so latitude and longitude cannot be read off directly.

Two implementations:
  to_geodetic_astropy  - accurate, uses astropy's TEME -> ITRS transform
  to_geodetic_fast     - GMST rotation + WGS-84 iteration, ~100x faster

The fast path is what the endpoints use. The astropy path exists so the
fast one can be checked against it.

Run directly to self-test:  python geodetic.py
"""

import numpy as np

# WGS-84
A_EARTH = 6378.137              # equatorial radius, km
F_EARTH = 1.0 / 298.257223563   # flattening
E2 = F_EARTH * (2.0 - F_EARTH)  # first eccentricity squared


def gmst_rad(jd, fr):
    """Greenwich Mean Sidereal Time in radians.

    IAU 1982 series. Accurate to well under an arcsecond over our
    horizon, which is far tighter than we need.
    """
    tut1 = (jd + fr - 2451545.0) / 36525.0
    secs = (67310.54841
            + (876600.0 * 3600.0 + 8640184.812866) * tut1
            + 0.093104 * tut1 ** 2
            - 6.2e-6 * tut1 ** 3)
    return np.deg2rad((secs % 86400.0) / 240.0) % (2.0 * np.pi)


def teme_to_ecef(r_teme, theta):
    """Rotate TEME into an Earth-fixed frame by the sidereal angle.

    Works on a single (3,) vector or an (n, 3) stack with matching theta.
    """
    r = np.atleast_2d(r_teme)
    th = np.atleast_1d(theta)
    c, s = np.cos(th), np.sin(th)
    x = c * r[:, 0] + s * r[:, 1]
    y = -s * r[:, 0] + c * r[:, 1]
    z = r[:, 2]
    return np.stack([x, y, z], axis=1)


def ecef_to_geodetic(r_ecef, iterations=5):
    """WGS-84 latitude, longitude, altitude from an Earth-fixed vector.

    Fixed-point iteration on latitude. Converges in three passes at
    orbital altitudes; five is free insurance.
    """
    r = np.atleast_2d(r_ecef)
    x, y, z = r[:, 0], r[:, 1], r[:, 2]

    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    lat = np.arctan2(z, p)

    # The altitude form below is p*cos(lat) + z*sin(lat) - A*sqrt(1-e2*sin^2),
    # which stays well conditioned at the poles. The naive p/cos(lat) - N
    # divides by zero there and poisons the next latitude update with NaN.
    for _ in range(iterations):
        sin_lat, cos_lat = np.sin(lat), np.cos(lat)
        root = np.sqrt(1.0 - E2 * sin_lat ** 2)
        n = A_EARTH / root
        alt = p * cos_lat + z * sin_lat - A_EARTH * root
        lat = np.arctan2(z, p * (1.0 - E2 * n / (n + alt)))

    sin_lat, cos_lat = np.sin(lat), np.cos(lat)
    root = np.sqrt(1.0 - E2 * sin_lat ** 2)
    alt = p * cos_lat + z * sin_lat - A_EARTH * root

    return np.rad2deg(lat), np.rad2deg(lon), alt


def to_geodetic_fast(r_teme, jd, fr):
    """TEME positions to (lat_deg, lon_deg, alt_km) arrays.

    r_teme is (n, 3) km; jd and fr are length-n.
    """
    theta = gmst_rad(np.asarray(jd), np.asarray(fr))
    return ecef_to_geodetic(teme_to_ecef(r_teme, theta))


def to_geodetic_astropy(r_teme, times):
    """Same conversion via astropy. Slower; used to verify the fast path."""
    from astropy import units as u
    from astropy.coordinates import ITRS, TEME, CartesianRepresentation
    from astropy.time import Time

    t = Time([x.replace(tzinfo=None) for x in times], scale="utc")
    rep = CartesianRepresentation(np.asarray(r_teme).T * u.km)
    itrs = TEME(rep, obstime=t).transform_to(ITRS(obstime=t))
    loc = itrs.earth_location.geodetic
    return (np.asarray(loc.lat.deg),
            np.asarray(loc.lon.deg),
            np.asarray(loc.height.to(u.km).value))


def track(r_teme, jd, fr, decimals=3):
    """The [lat, lon, alt_km] list the API contract promises."""
    lat, lon, alt = to_geodetic_fast(r_teme, jd, fr)
    return [[round(float(a), decimals),
             round(float(b), decimals),
             round(float(c), 2)]
            for a, b, c in zip(lat, lon, alt)]


if __name__ == "__main__":
    import time as _t

    import ingest
    import propagate

    cat = ingest.load()
    sats, meta = propagate.build(cat)
    idx = propagate.find(meta, 25544)
    if idx is None:
        raise SystemExit("ISS not in catalog")

    jd, fr, times = propagate.time_grid(hours=1.5, step_s=60)
    err, r, v = propagate.propagate(sats, jd, fr)
    iss = r[idx]

    t0 = _t.time()
    lat_f, lon_f, alt_f = to_geodetic_fast(iss, jd, fr)
    fast_ms = (_t.time() - t0) * 1000

    print("check 1  ground track sanity")
    print(f"  lat range : {lat_f.min():7.2f} to {lat_f.max():7.2f} deg "
          f"(ISS inclination is 51.6, so expect about -51.6 to 51.6)")
    print(f"  alt range : {alt_f.min():7.2f} to {alt_f.max():7.2f} km "
          f"(expect roughly 400-430)")
    print(f"  lon spans : {lon_f.min():7.2f} to {lon_f.max():7.2f} deg\n")

    try:
        t0 = _t.time()
        lat_a, lon_a, alt_a = to_geodetic_astropy(iss, times)
        astro_ms = (_t.time() - t0) * 1000

        d_lat = np.abs(lat_f - lat_a).max()
        d_lon = np.abs(((lon_f - lon_a + 180) % 360) - 180).max()
        d_alt = np.abs(alt_f - alt_a).max()

        print("check 2  fast path vs astropy")
        print(f"  max lat error : {d_lat * 111.0:8.3f} km  ({d_lat:.5f} deg)")
        print(f"  max lon error : {d_lon * 111.0:8.3f} km  ({d_lon:.5f} deg)")
        print(f"  max alt error : {d_alt:8.3f} km")
        print(f"  fast {fast_ms:.1f} ms vs astropy {astro_ms:.1f} ms "
              f"({astro_ms / max(fast_ms, 0.01):.0f}x)\n")
        if max(d_lat, d_lon) * 111.0 < 5.0:
            print("  agreement is well inside what a 3D globe can show.")
        else:
            print("  DISAGREEMENT - investigate before trusting the fast path.")
    except Exception as e:
        print(f"check 2  astropy comparison skipped: {e}\n")

    print("check 3  contract shape")
    t = track(iss[:3], jd[:3], fr[:3])
    for row in t:
        print(f"  {row}")