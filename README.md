# F1-Zoom

F1-Zoom is a full-stack Formula 1 app built by the Monash DeepNeuron team. It pulls race weekend data from FastF1, stores it in Supabase, trains a ranking model to predict the next Grand Prix, and serves everything through a React frontend with 3D circuit visuals and a live timing view.

The goal was to go beyond a static stats page. We wanted something that feels like race weekend: a circuit you can explore, predictions that update as new sessions land, and a live page that can follow a session in real time.

## What we built

### Frontend (`frontend/`)

A React + TypeScript app with four main routes:

- **Home** (`/`): A Three.js circuit hero that loads the track for the upcoming race. Below that you get predicted top-10 results, driver and constructor standings, next race info, and a season calendar map. On first visit, a short cinematic intro zooms into the circuit and drops you into a playable pixel mini game on the same track layout.
- **Predictions** (`/predictions`): Full predicted classification for all 20 drivers, with model scores, grid comparison, and a written insight generated from the weekend data.
- **Live** (`/live`): Live timing board and track map fed by Server-Sent Events. Works against a mock replay by default, or the official F1 SignalR feed when configured.
- **About** (`/about`): A breakdown of the prediction pipeline, model settings, and the feature columns the ranker uses.

Track geometry lives in `frontend/public/circuit_3d/`. We have centreline coordinates for 23 of the 24 circuits on the 2026 calendar (Madrid is the one still missing). CSVs are converted to JS modules for the renderer, with corner markers derived from curvature in the source data.

### Backend (`backend/`)

A Spring Boot API on port 8080. It proxies the Ergast F1 API for championship standings, race schedule, and next/last race info. Circuit metadata, session times, past winners, stored predictions, and AI insights come from Supabase.

Base path: `/api/v1`

### Data pipeline (`data_pipeline/`)

Python scripts that run after each session finishes. The orchestrator looks for sessions that ended more than two hours ago but have not been ingested yet, fetches results and lap telemetry from FastF1, and writes structured rows to Supabase.

From that raw data we compute:

- Practice, qualifying, and race session results per driver
- Lap-level pace, clean-air pace, speed ranks, and tyre metrics
- Rolling 3-, 5-, and 7-race form with a one-race lag so nothing leaks into training
- Track-level stats (overtakes, safety car rates, red flag frequency)

After predictions are written, `ai_insights.py` calls Gemini to produce a short summary, key reasons, contenders, and caveats for the Predictions page.

A GitHub Actions workflow (`.github/workflows/f1-data-pipeline.yml`) runs the orchestrator and retrains the model every two hours, or on manual trigger.

### Prediction model (`Data/Simulation/`)

We use a **LightGBM LambdaRank** model rather than predicting a raw finishing position. Each race is one group, and the model learns to rank drivers within that group, optimised for NDCG. That matches how F1 results actually work: you care about relative order, not an absolute number.

Inputs include grid position, practice and qualifying times, pace deltas, speed metrics, track characteristics, and rolling history. After each race weekend the model is retrained from Supabase (or from the local CSV fallback) and predictions for the next Grand Prix are stored back in Supabase.

`prediction_service.py` exposes a FastAPI API on port 8000. The Spring Boot backend reads predictions from Supabase directly, so the frontend does not need the Python service running for normal use. The FastAPI layer is still useful for local testing and direct model access.

### Live timing service (`live_service/`)

A FastAPI service that maintains in-memory session state and broadcasts incremental updates over SSE. In mock mode it replays timing against a local track file. Set `F1_MODE=live` to connect to the official feed via `f1_client.py`.

The frontend proxies `/api/realtime` and `/api/state` to this service through Vite.

## How data flows

```
FastF1  -->  data_pipeline orchestrator  -->  Supabase
                                                  |
                                                  v
                                    LightGBM ranker (retrain + predict)
                                                  |
                                                  v
                              Spring Boot API  <--  React frontend
                                                  ^
Live F1 feed / mock replay  -->  live_service (SSE) --+
```

1. Sessions finish. The pipeline ingests FP, qualifying, sprint, and race data.
2. Features are computed and stored alongside per-driver race entries.
3. The ranker retrains and writes predicted positions to Supabase.
4. Gemini generates a human-readable insight for the top of the grid.
5. The frontend reads everything through the Spring Boot API. The Live page connects separately to the timing service.

## Repository structure

```
F1-Zoom/
├── backend/                 Spring Boot API (Java 21)
├── frontend/                React + Vite + Three.js
│   └── public/circuit_3d/   Track CSV/JS assets and generators
├── Data/Simulation/         LightGBM training and prediction API
├── live_service/            FastAPI SSE live/mock timing
├── data_pipeline/           FastF1 ETL, feature engineering, AI insights
├── .github/workflows/       Scheduled pipeline + model retrain
├── .env.example             Environment variable template
└── README.md
```

## Prerequisites

- Java 21+
- Node.js 18+ and npm
- Python 3.11+ (Conda works well)
- Maven is optional if you use `./mvnw`

## Environment variables

Copy the template and fill in your values:

```bash
cp .env.example .env
```

Required for Supabase-backed features (pipeline, circuits, predictions):

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Optional:

- `GEMINI_API_KEY` for AI-written prediction insights

## Setup

### Backend

```bash
cd backend
./mvnw clean install
./mvnw spring-boot:run
```

Runs at `http://localhost:8080`. Try `GET /api/v1/test` to confirm it is up.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Runs at `http://localhost:5173`.

Vite proxies:

- `/api/realtime` and `/api/state` -> `http://localhost:8000` (live timing)
- `/api` -> `http://localhost:8080` (Spring Boot)

### Python environment

```bash
conda create -n f1-project python=3.11 -y
conda activate f1-project
```

### Data pipeline

```bash
cd data_pipeline
pip install -r requirements.txt
```

Run from the project root:

```bash
python -m data_pipeline.orchestrator
```

### Prediction model

```bash
cd Data/Simulation
pip install -r requirements.txt
python lightgbm_model.py --from-supabase --auto
python prediction_service.py   # optional, for direct API access
```

### Live timing

```bash
cd live_service
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Mock mode is the default. For the live feed:

```bash
F1_MODE=live uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Useful env vars: `F1_MODE=mock|live`, `TRACK_NAME=Melbourne`, `TRACK_DATA_DIR=/path/to/TrackCoordinateJS`

**Port note:** `prediction_service.py` and `live_service` both default to port 8000. Run one at a time on that port, or move one service and update the Vite proxy in `frontend/vite.config.ts`.

## Common run combinations

### Frontend + backend (typical browsing)

```bash
# Terminal 1
cd backend && ./mvnw spring-boot:run

# Terminal 2
cd frontend && npm run dev
```

Predictions and circuit data come from Supabase, so the pipeline and model need to have run at least once (locally or via GitHub Actions).

### Frontend + backend + live timing (mock)

```bash
# Terminal 1
cd backend && ./mvnw spring-boot:run

# Terminal 2
cd live_service && uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3
cd frontend && npm run dev
```

Then open `/live`.

## Track coordinate tooling

Convert CSV tracks to JS assets for the renderer:

```bash
cd frontend/public/circuit_3d
python csv_reading.py
```

Generate missing track CSVs from FastF1:

```bash
cd frontend/public/circuit_3d
python generate_missing_track_csvs_fastf1.py
```

Compare a generated Melbourne variant against the current baseline:

```bash
cd frontend/public/circuit_3d
python compare_melbourne_fastf1.py
```

See `frontend/public/circuit_3d/TrackCoordinateCSVs/F1_Track_Coordinate_Coverage.md` for which circuits are covered.

## Testing and build

Backend:

```bash
cd backend
./mvnw test
./mvnw clean package
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
npm run preview
```

## Notes

- Supabase credentials are required for the data pipeline and for circuit/prediction endpoints on the backend.
- The About page (`/about`) documents every feature column the ranker consumes. That list is kept in sync with `Data/Simulation/lightgbm_model.py`.
- If predictions show as unavailable, check that the GitHub Actions workflow has run successfully or execute the orchestrator and model scripts locally.
- The 3D track renderer and mini game share the same coordinate files under `frontend/public/circuit_3d/TrackCoordinateJS/`. Some street circuits still have rough geometry; corner detection and direction are active areas of work.
