import numpy as np


def collision_probability(miss_distance_km: float, combined_hard_body_radius_km: float, position_covariance) -> float:
    sigma = float(np.sqrt(np.trace(position_covariance)))
    if sigma == 0:
        return 0.0
    return float(np.exp(-(miss_distance_km ** 2) / (2 * sigma ** 2)))
