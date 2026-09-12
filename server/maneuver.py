import numpy as np


def plan_dodge(velocity, delta_v_km_s: float, direction):
    direction = np.array(direction) / np.linalg.norm(direction)
    new_velocity = np.array(velocity) + direction * delta_v_km_s
    return new_velocity.tolist()
