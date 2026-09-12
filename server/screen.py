import numpy as np


def distance(position_a, position_b) -> float:
    return float(np.linalg.norm(np.array(position_a) - np.array(position_b)))


def find_close_approaches(objects, threshold_km: float):
    close_approaches = []
    for i in range(len(objects)):
        for j in range(i + 1, len(objects)):
            if distance(objects[i]["position"], objects[j]["position"]) <= threshold_km:
                close_approaches.append((objects[i], objects[j]))
    return close_approaches
