import json, os, asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

app = FastAPI()
FIX = os.path.join(os.path.dirname(__file__), "fixtures")

def fixture(name):
    path = os.path.join(FIX, name)
    if not os.path.exists(path):
        raise HTTPException(404, f"no fixture: {name}")
    with open(path) as f:
        return json.load(f)

@app.get("/api/status")
def status():
    return fixture("status.json")

@app.get("/api/conjunctions")
def conjunctions():
    return fixture("conjunctions.json")

@app.get("/api/conjunctions/{cdm_id}")
def conjunction(cdm_id: str):
    return fixture(f"conjunction_{cdm_id}.json")

@app.get("/api/ephemeris/{cdm_id}")
def ephemeris(cdm_id: str):
    return fixture(f"ephemeris_{cdm_id}.json")

@app.get("/api/debris-cloud")
def debris():
    return fixture("debris_cloud.json")

@app.get("/api/plan/{cdm_id}")
def get_plan(cdm_id: str):
    return fixture(f"plan_{cdm_id}.json")

@app.post("/api/plan/{cdm_id}")
def make_plan(cdm_id: str):
    return fixture(f"plan_{cdm_id}.json")

@app.post("/api/coordinate/{cdm_id}")
def coordinate(cdm_id: str):
    return fixture(f"coordinate_{cdm_id}.json")

@app.get("/api/ledger")
def ledger():
    return fixture("ledger.json")

@app.get("/api/density")
def density():
    return fixture("density.json")

@app.get("/api/events")
async def events():
    async def gen():
        for e in fixture("events.json"):
            yield f"data: {json.dumps(e)}\n\n"
            await asyncio.sleep(1.5)
    return StreamingResponse(gen(), media_type="text/event-stream")
