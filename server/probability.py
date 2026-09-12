"""Collision probability for Aegis OTM.

Free TLE/GP data carries no covariance, so we synthesise one and say so
openly. Everything below is honest about its assumptions - put them on a
slide rather than hiding them.

Method: Foster's 2D approach. Both objects move fast enough that the
encounter is effectively instantaneous, so the 3D problem collapses onto
the plane perpendicular to the relative velocity vector. Collision
probability is then the fraction of a 2D Gaussian falling inside a circle
of the combined hard-body radius.

Run directly to self-test:  python probability.py
"""

import numpy as np

# --- Assumption 1: synthetic covariance -------------------------------
# 1-sigma position uncertainty at the TLE epoch, in metres, in the RTN
# frame. In-track is much larger than the others because along-track
# position is the least well-determined part of any orbit. Real operators
# would supply their own orbit determination covariance instead.
SIGMA_AT_EPOCH_M = {"radial": 300.0, "in_track": 1500.0, "cross_track": 300.0}

# Uncertainty grows as the tracking data ages. Between linear and
# quadratic; 1.5 is a common engineering choice.
GROWTH_EXPONENT = 1.5
REFERENCE_AGE_H = 24.0

# Floor on the 1-sigma values. Very fresh tracking data would otherwise
# scale the uncertainty down to a few tens of metres, which no real orbit
# determination process achieves for an uncooperative object.
MIN_SIGMA_M = 150.0

# --- Assumption 2: hard-body radius -----------------------------------
# The GP feed has no RCS_SIZE field (that lives in CelesTrak's separate
# SATCAT), so default every object to 1 m and map size classes when we
# do have them.
DEFAULT_RADIUS_M = 1.0
RADIUS_BY_SIZE = {"SMALL": 0.5, "MEDIUM": 2.0, "LARGE": 5.0}

RED_PC = 1e-4
AMBER_PC = 1e-5


# ------------------------------------------------------------- covariance

def epoch_age_hours(epoch_iso, now=None):
    """Hours between a TLE epoch and now."""
    from datetime import datetime, timezone
    if now is None:
        now = datetime.now(timezone.utc)
    s = str(epoch_iso)
    if "." not in s:
        s += ".000000"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return REFERENCE_AGE_H
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (now - dt).total_seconds() / 3600.0)


def covariance_rtn(age_hours, lead_hours=0.0):
    """3x3 diagonal position covariance in the RTN frame, in m^2.

    Uncertainty grows with two things: how old the tracking data is, and
    how far ahead of it we are predicting. At a 72 hour screening horizon
    the lead time dominates - which is why real conjunction assessment
    covariances reach kilometres, not tens of metres.

    Diagonal because we have no cross-correlation information to work
    with - another stated simplification.
    """
    effective_h = max(age_hours, 1.0) + max(lead_hours, 0.0)
    scale = (effective_h / REFERENCE_AGE_H) ** GROWTH_EXPONENT
    s = np.array([
        SIGMA_AT_EPOCH_M["radial"],
        SIGMA_AT_EPOCH_M["in_track"],
        SIGMA_AT_EPOCH_M["cross_track"],
    ]) * scale
    s = np.maximum(s, MIN_SIGMA_M)
    return np.diag(s ** 2)


def rtn_basis(r, v):
    """Rows are the RTN unit vectors, so B @ x maps ECI -> RTN."""
    R = r / np.linalg.norm(r)
    N = np.cross(r, v)
    N = N / np.linalg.norm(N)
    T = np.cross(N, R)
    return np.vstack([R, T, N])


def covariance_eci(r, v, age_hours, lead_hours=0.0):
    """Rotate the RTN covariance into the inertial frame."""
    B = rtn_basis(r, v)
    C_rtn = covariance_rtn(age_hours, lead_hours)
    return B.T @ C_rtn @ B


# ----------------------------------------------------------- hard body

def hard_body_radius_m(meta_a, meta_b):
    """Combined radius of the two objects, in metres."""
    def radius(m):
        size = (m or {}).get("rcs_size")
        return RADIUS_BY_SIZE.get(size, DEFAULT_RADIUS_M)
    return radius(meta_a) + radius(meta_b)


# ------------------------------------------------------ encounter plane

def encounter_plane(r_a, v_a, r_b, v_b, cov_a, cov_b):
    """Project the relative geometry onto the 2D encounter plane.

    The plane is perpendicular to the relative velocity. Its axes are
    chosen so that x lies along the projected miss direction, which makes
    the result easy to plot.

    Returns a dict with the 2D miss vector, the 2x2 combined covariance,
    and the solved ellipse parameters.
    """
    dr = (r_b - r_a) * 1000.0                  # km -> m
    dv = (v_b - v_a) * 1000.0                  # km/s -> m/s

    v_hat = dv / np.linalg.norm(dv)

    # Two orthonormal axes spanning the plane normal to relative velocity.
    seed = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(seed, v_hat)) > 0.9:
        seed = np.array([0.0, 0.0, 1.0])
    e1 = seed - np.dot(seed, v_hat) * v_hat
    e1 = e1 / np.linalg.norm(e1)
    e2 = np.cross(v_hat, e1)

    P = np.vstack([e1, e2])                    # (2, 3) projection

    miss2 = P @ dr
    C2 = P @ (cov_a + cov_b) @ P.T             # combined, projected

    # Solve the ellipse once here so the frontend never has to.
    vals, vecs = np.linalg.eigh(C2)
    order = np.argsort(vals)[::-1]
    vals, vecs = vals[order], vecs[:, order]
    sigma_major = float(np.sqrt(max(vals[0], 1e-12)))
    sigma_minor = float(np.sqrt(max(vals[1], 1e-12)))
    rotation = float(np.degrees(np.arctan2(vecs[1, 0], vecs[0, 0])))

    return {
        "miss_x_m": float(miss2[0]),
        "miss_y_m": float(miss2[1]),
        "sigma_major_m": sigma_major,
        "sigma_minor_m": sigma_minor,
        "rotation_deg": rotation,
        "_cov2": C2,
        "_miss2": miss2,
    }


# ---------------------------------------------------------------- the Pc

def collision_probability(miss2, cov2, hbr_m, n_r=120, n_theta=240):
    """Integrate the 2D Gaussian over a circle of radius hbr_m.

    Polar grid centred on the hard-body circle. No clever closed form -
    numerical integration is accurate enough and far easier to verify.
    """
    if hbr_m <= 0:
        return 0.0

    det = np.linalg.det(cov2)
    if det <= 0:
        return 0.0
    inv = np.linalg.inv(cov2)
    norm = 1.0 / (2.0 * np.pi * np.sqrt(det))

    # Midpoint rule in polar coordinates.
    dr = hbr_m / n_r
    dth = 2.0 * np.pi / n_theta
    rr = (np.arange(n_r) + 0.5) * dr
    th = (np.arange(n_theta) + 0.5) * dth

    R, TH = np.meshgrid(rr, th, indexing="ij")
    X = R * np.cos(TH) - miss2[0]
    Y = R * np.sin(TH) - miss2[1]

    q = (inv[0, 0] * X * X + 2.0 * inv[0, 1] * X * Y + inv[1, 1] * Y * Y)
    pdf = norm * np.exp(-0.5 * q)

    # area element r dr dtheta
    return float(np.sum(pdf * R) * dr * dth)


def risk_band(pc):
    if pc >= RED_PC:
        return "RED"
    if pc >= AMBER_PC:
        return "AMBER"
    return "GREEN"


# ------------------------------------------------------------- top level

def assess(r_a, v_a, r_b, v_b, meta_a, meta_b, now=None, lead_hours=0.0):
    """Full assessment for one conjunction.

    Positions in km, velocities in km/s, both in the inertial frame at TCA.
    lead_hours is the time from now to TCA, which drives most of the
    uncertainty growth at long screening horizons.

    Returns the encounter-plane payload the API contract promises.
    """
    age_a = epoch_age_hours(meta_a.get("epoch"), now)
    age_b = epoch_age_hours(meta_b.get("epoch"), now)

    cov_a = covariance_eci(r_a, v_a, age_a, lead_hours)
    cov_b = covariance_eci(r_b, v_b, age_b, lead_hours)

    ep = encounter_plane(r_a, v_a, r_b, v_b, cov_a, cov_b)
    hbr = hard_body_radius_m(meta_a, meta_b)
    pc = collision_probability(ep["_miss2"], ep["_cov2"], hbr)

    return {
        "miss_x_m": round(ep["miss_x_m"], 1),
        "miss_y_m": round(ep["miss_y_m"], 1),
        "sigma_major_m": round(ep["sigma_major_m"], 1),
        "sigma_minor_m": round(ep["sigma_minor_m"], 1),
        "rotation_deg": round(ep["rotation_deg"], 1),
        "hbr_m": round(hbr, 2),
        "pc": pc,
        "risk": risk_band(pc),
        "tle_age_hours": {"primary": round(age_a, 1),
                          "secondary": round(age_b, 1)},
        "lead_hours": round(lead_hours, 1),
    }


def assumptions():
    """Shipped to the frontend and reproduced on the slides."""
    return {
        "covariance_source": "synthetic",
        "sigma_at_epoch_m": SIGMA_AT_EPOCH_M,
        "growth_exponent": GROWTH_EXPONENT,
        "reference_age_hours": REFERENCE_AGE_H,
        "min_sigma_m": MIN_SIGMA_M,
        "hbr_source": "default 1 m per object; GP feed has no RCS_SIZE",
        "growth_driver": "TLE age + time to TCA (lead time dominates at 72h)",
        "method": "Foster 2D encounter plane, numerical polar integration",
    }


if __name__ == "__main__":
    # Check 1: against the closed-form answer for a centred circular
    # Gaussian, where Pc = 1 - exp(-hbr^2 / 2*sigma^2).
    C = np.diag([100.0 ** 2, 100.0 ** 2])
    pc = collision_probability(np.array([0.0, 0.0]), C, 5.0)
    exact = 1.0 - np.exp(-(5.0 ** 2) / (2 * 100.0 ** 2))
    print("check 1  centred circular Gaussian, 100 m sigma, 5 m hard body")
    print(f"  integrated : {pc:.6e}")
    print(f"  closed form: {exact:.6e}")
    print(f"  ratio      : {pc / exact:.5f}   (want 1.00000)\n")

    # Check 2: Pc must fall monotonically as the miss distance grows.
    print("check 2  Pc vs miss distance")
    for d in [0, 50, 100, 200, 500, 1000]:
        p = collision_probability(np.array([float(d), 0.0]), C, 5.0)
        print(f"  {d:>5} m -> {p:.3e}  {risk_band(p)}")

    # Check 3: full assessment path, synthetic crossing geometry.
    from datetime import datetime, timezone
    now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    r_a = np.array([6800.0, 0.0, 0.0])
    v_a = np.array([0.0, 7.6, 0.0])
    r_b = np.array([6800.2, 0.1, 0.3])
    v_b = np.array([0.0, -7.5, 1.0])
    ma = {"epoch": "2026-09-12T00:00:00.000000"}
    mb = {"epoch": "2026-09-11T00:00:00.000000"}

    print("\ncheck 3  full assess() on a synthetic head-on crossing")
    for k, val in assess(r_a, v_a, r_b, v_b, ma, mb, now=now).items():
        print(f"  {k}: {val}")

    print("\nassumptions shipped to the frontend:")
    for k, val in assumptions().items():
        print(f"  {k}: {val}")