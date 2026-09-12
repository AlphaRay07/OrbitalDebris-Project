from probability import collision_probability
from screen import find_close_approaches

TOOLS = [
    {
        "name": "find_close_approaches",
        "description": "Find pairs of tracked objects that come within a distance threshold of each other.",
        "input_schema": {
            "type": "object",
            "properties": {
                "threshold_km": {"type": "number"},
            },
            "required": ["threshold_km"],
        },
    },
    {
        "name": "collision_probability",
        "description": "Estimate the probability of collision for a close approach.",
        "input_schema": {
            "type": "object",
            "properties": {
                "miss_distance_km": {"type": "number"},
                "combined_hard_body_radius_km": {"type": "number"},
            },
            "required": ["miss_distance_km", "combined_hard_body_radius_km"],
        },
    },
]


def call_tool(name: str, tool_input: dict, objects=None):
    if name == "find_close_approaches":
        return find_close_approaches(objects or [], tool_input["threshold_km"])
    if name == "collision_probability":
        return collision_probability(
            tool_input["miss_distance_km"],
            tool_input["combined_hard_body_radius_km"],
            tool_input.get("position_covariance", [[1, 0, 0], [0, 1, 0], [0, 0, 1]]),
        )
    raise ValueError(f"Unknown tool: {name}")
