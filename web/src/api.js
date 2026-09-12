const BASE = "/fixtures";          // hour 1–7
// const BASE = "http://localhost:8010/api";   // hour 7 onward, one-line change

const get = async (path) => {
    const res = await fetch(`${BASE}${path}`);
    const contentType = res.headers.get("content-type");
    if (!res.ok || (contentType && contentType.includes("text/html"))) {
        throw new Error(`${path} → ${res.status} (Not Found or HTML fallback)`);
    }
    return res.json();
};

export const getStatus = () => get("/status.json");
export const getConjunctions = () => get("/conjunctions.json");

export const getConjunction = async (id) => {
    try {
        return await get(`/conjunction_${id}.json`);
    } catch (err) {
        // Fallback to primary CDM-0001 fixture if individual CDM fixture is not in /fixtures/
        return await get("/conjunction_CDM-0001.json");
    }
};

export const getEphemeris = async (id) => {
    try {
        return await get(`/ephemeris_${id}.json`);
    } catch (err) {
        // Fallback to primary CDM-0001 ephemeris fixture
        return await get("/ephemeris_CDM-0001.json");
    }
};

export const getDebrisCloud = () => get("/debris_cloud.json");

export const getPlan = async (id) => {
    try {
        return await get(`/plan_${id}.json`);
    } catch (err) {
        return await get("/plan_CDM-0001.json");
    }
};

export const getLedger = () => get("/ledger.json");
export const getDensity = () => get("/density.json");

