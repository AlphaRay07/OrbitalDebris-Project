// const BASE = "/fixtures";          // hour 1–7: static fixtures
const BASE = "http://localhost:8010/api";   // hour 7 onward: live backend server

const get = async (path) => {
    const res = await fetch(`${BASE}${path}`);
    if (!res.ok) throw new Error(`${path} → ${res.status}`);
    return res.json();
};

export const getStatus = () => get("/status");
export const getConjunctions = () => get("/conjunctions");

export const getConjunction = (id) => get(`/conjunctions/${id}`);
export const getEphemeris   = (id) => get(`/ephemeris/${id}`);

export const getDebrisCloud = () => get("/debris-cloud");

export const getPlan = (id) => get(`/plan/${id}`);

export const getLedger = () => get("/ledger");
export const getDensity = () => get("/density");

// Trigger Endpoints for Live Operations & Agents
const post = async (path, body = {}) => {
    const res = await fetch(`${BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`${path} → ${res.status}`);
    return res.json();
};

export const runAgents       = (width = 1, cdmId = null) => 
    post(`/agents/run?width=${width}${cdmId ? `&cdm_id=${cdmId}` : ''}`);

export const publishIntent    = (cdmId, maneuverId, operator = "NASA") =>
    post("/ledger/publish", { cdm_id: cdmId, maneuver_id: maneuverId, operator });

export const runSingleAgent  = (agent, cdmId = "CDM-0001") => post(`/agents/${agent}?cdm_id=${cdmId}`);
export const runScreening    = (asset = "25544", horizon = 72, threshold = 50.0) => 
    post(`/screen?asset_norad=${asset}&hours=${horizon}&threshold_km=${threshold}`);
export const runCascadeCheck = (cdmId = "CDM-0001") => post(`/plan/${cdmId}/cascade`);

