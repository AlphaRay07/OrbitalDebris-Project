import httpx, json, os

URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP={g}&FORMAT=json"
GROUPS = ["active", "cosmos-1408-debris", "fengyun-1c-debris",
          "iridium-33-debris", "cosmos-2251-debris"]
CACHE = os.path.join(os.path.dirname(__file__), "cache")


def fetch():
    os.makedirs(CACHE, exist_ok=True)
    objects = []
    for g in GROUPS:
        r = httpx.get(URL.format(g=g), timeout=60)
        r.raise_for_status()
        data = r.json()
        for o in data:
            o["_group"] = g
        objects += data
        print(f"{g}: {len(data)}")
    with open(os.path.join(CACHE, "catalog.json"), "w") as f:
        json.dump(objects, f)
    return objects


def load():
    with open(os.path.join(CACHE, "catalog.json")) as f:
        return json.load(f)


if __name__ == "__main__":
    print("total:", len(fetch()))