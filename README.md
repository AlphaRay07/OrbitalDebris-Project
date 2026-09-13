# Aegis OTM — Autonomous Orbital Traffic Management System

Aegis OTM is an autonomous multi-agent space traffic management network designed to detect LEO orbital conjunctions, optimize collision avoidance maneuvers, screen secondary debris cascade risks, and publish tamper-evident deconfliction intents to a shared cryptographic ledger.

Built for the **Bit N Build Hackathon** by **Manav Dewan** and **Satwik**.

---

## 🚀 Key Features

- **Real-Time SGP4 Screening & Physics Engine**: Propagates orbital ephemerides for active payloads and catalog space debris over a 72-hour horizon. Calculates 3D covariance collision probabilities ($P_c$) using the Foster (1992) encounter-plane reduction formulation.
- **96-Candidate Maneuver Optimization**: Evaluates 96 impulsive along-track burn options ($\Delta v$ from $0.5\text{ mm/s}$ to $100\text{ mm/s}$) across multiple lead orbits, balancing propellant cost against collision risk reduction.
- **Automated Debris Cascade Re-screening**: Evaluates proposed avoidance maneuvers against background catalog debris traffic to ensure an avoidance burn does not trigger a secondary collision.
- **Physics-Grounded Multi-Agent Orchestration**: Four autonomous specialized agents (`TRACKER`, `SCREENER`, `PLANNER`, `COORDINATOR`) handle threat triage, right-of-way negotiation, and action logging. All numerical calculations are strictly computed by deterministic Python physics engines.
- **Cryptographic Intent Ledger**: Implements SHA-256 hash chaining (`prev_hash | cdm_id | maneuver_id | burn_epoch | delta_v`) to publish verifiable, tamper-evident coordination entries and prevent orbital pathway double-booking.
- **Mission Control Operations Dashboard**: High-contrast, dark-mode React interface featuring live Server-Sent Events (SSE) streaming, interactive Pareto trade-off charts, and 1-click intent publishing.

---

## 🏗️ System Architecture

```text
               +-------------------------------------------------+
               |             CelesTrak / Space-Track             |
               |            TLE Orbital Catalog Stream           |
               +-----------------------+-------------------------+
                                       |
                                       v
               +-------------------------------------------------+
               |            SGP4 Orbit Screening Engine          |
               |           72h Horizon & Foster 1992 Pc          |
               +-----------------------+-------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------------+
|                            MULTI-AGENT ORCHESTRATOR                               |
|                                                                                   |
|  [TRACKER]     ---> Validates catalog freshness and tracking data quality.         |
|  [SCREENER]    ---> Assesses close approaches & classifies risk (RED/AMBER/GREEN). |
|  [PLANNER]     ---> Solves 96 burn candidates & evaluates cascade safety.          |
|  [COORDINATOR] ---> Applies Right-of-Way rules & triggers intent publication.      |
+--------------------------------------+--------------------------------------------+
                                       |
                                       v
               +-------------------------------------------------+
               |          SHA-256 Cryptographic Intent           |
               |             Shared Operation Ledger             |
               +-----------------------+-------------------------+
                                       |
                                       v
               +-------------------------------------------------+
               |      React Vite Mission Control Dashboard       |
               |         (SSE Stream & Pareto Chart UI)          |
               +-------------------------------------------------+
```

---

## 📊 Operational Workflow

1. **Catalog Ingestion & Screening**: SGP4 propagates satellite positions to detect close approaches within specified distance thresholds.
2. **Threat Assessment**: `SCREENER` categorizes events by collision probability $P_c$ into **RED** ($\ge 10^{-4}$), **AMBER** ($10^{-5}\text{ to }10^{-4}$), and **GREEN** ($< 10^{-5}$).
3. **Maneuver Planning & Cascade Re-Screening**: `PLANNER` searches along-track prograde/retrograde burn vectors, screens for secondary cascade collisions, and constructs a Pareto frontier ($\Delta v$ vs. $P_c$).
4. **Deconfliction & Intent Publication**: `COORDINATOR` applies right-of-way priority rules (*Crewed Payload > Active Payload > Derelict/Debris*) and commits the cryptographic SHA-256 transaction hash to the open ledger.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.12, FastAPI, Uvicorn, Asyncio
- **Physics & Mathematics**: `sgp4`, `numpy`, `scipy`
- **Multi-Agent Engine**: Custom async state machine with LLM tool-calling (Gemini / Ollama support)
- **Frontend**: React 18, Vite, Tailwind CSS, Lucide Icons, Server-Sent Events (SSE)
- **Database & Ledger**: In-Memory state store with persistent JSON caching & SHA-256 cryptographic hashing

---

## ⚡ Getting Started

### Prerequisites
- Node.js (v18+)
- Python (v3.10+)

### 1. Start the Backend API Server
```bash
cd server
pip install -r requirements.txt
python -m uvicorn app:app --reload --port 8010
```

### 2. Start the Frontend Dashboard
```bash
cd web
npm install
npm run dev
```

Open `http://localhost:5173` in your browser to access the Aegis OTM Mission Control Dashboard.

---

## 📡 Core API Endpoints

- `GET /api/status`: System telemetry and catalog staleness metrics.
- `GET /api/conjunctions`: Ranked close approaches and risk band summaries.
- `GET /api/conjunctions/{cdm_id}`: Detailed geometry and covariance ellipse metrics.
- `GET /api/plan/{cdm_id}`: 96-candidate Pareto maneuver options and cascade check results.
- `POST /api/agents/run`: Triggers the 4-agent autonomous pipeline for a targeted CDM threat.
- `POST /api/ledger/publish`: Commits a selected maneuver option to the SHA-256 cryptographic intent ledger.
- `GET /api/ledger`: Retrieves published ledger transaction history.
- `GET /api/events`: Server-Sent Events (SSE) live streaming feed for agent reasoning logs.

---

## 👥 Contributors

- **Manav Dewan** - [*@AlphaRay07*](https://github.com/AlphaRay07)
- **Satwik**

---

*Built with ❤️ for the Bit N Build Hackathon.*
