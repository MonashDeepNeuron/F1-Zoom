# F1-Zoom

F1-Zoom is a multi-service project for Formula 1 data, visualization, and predictions.

It includes:

- A React + Vite frontend
- A Spring Boot backend API
- A FastAPI prediction service (LightGBM)
- A FastAPI live timing service (mock or live SignalR feed)
- A Python data pipeline for collecting and writing race/session data

## Architecture

Typical app flow:

- Frontend (`frontend`) on `http://localhost:5173`
- Backend (`backend`) on `http://localhost:8080`
- Prediction service (`Data/Simulation`) on `http://localhost:8000`
- Live timing service (`live_service`) on `http://localhost:8000` by default

Important port note:

- `prediction_service.py` and `live_service/main.py` both default to port `8000`.
- Run one at a time on `8000`, or move one service to another port and update callers/proxy config.

## Repository Structure

```text
F1-Zoom/
├── backend/                 # Spring Boot API (Java 21, Maven wrapper)
│   ├── src/main/java/
│   ├── src/main/resources/
│   ├── pom.xml
│   └── mvnw
├── frontend/                # React + TypeScript + Vite app
│   ├── src/
│   ├── public/circuit_3d/   # Track CSV/JS assets + converters/generators
│   └── package.json
├── Data/Simulation/         # LightGBM model training + FastAPI prediction API
│   ├── lightgbm_model.py
│   ├── prediction_service.py
│   ├── requirements.txt
│   └── README.md
├── live_service/            # FastAPI SSE service for live/mock timing
│   ├── main.py
│   ├── mock.py
│   ├── f1_client.py
│   └── requirements.txt
├── data_pipeline/           # Supabase/FastF1 ETL and feature generation scripts
│   ├── orchestrator.py
│   ├── db/
│   ├── fetchers/
│   └── requirements.txt
├── .env.example             # Required environment variable template
└── README.md
```

## Prerequisites

Install these first:

- Java 21+
- Node.js 18+ and npm
- Python 3.11+ (Conda recommended)
- Maven is optional if you use `./mvnw`

## Environment Variables

Copy and fill environment values:

```bash
cp .env.example .env
```

Required for Supabase-backed features:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

## Setup

### 1) Backend Setup (Spring Boot)

```bash
cd backend
./mvnw clean install
```

Run backend:

```bash
./mvnw spring-boot:run
```

Backend API base path is `/api/v1` (for example `/api/v1/test`).

### 2) Frontend Setup (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`.

Vite proxy is configured to:

- `/api/realtime` -> `http://localhost:8000`
- `/api/state` -> `http://localhost:8000`
- `/api` -> `http://localhost:8080`

### 3) Python Environment

If using conda:

```bash
conda create -n f1-project python=3.11 -y
conda activate f1-project
```

### 4) Prediction Service Setup (Data/Simulation)

Install deps:

```bash
cd Data/Simulation
pip install -r requirements.txt
```

Train model (first run):

```bash
python lightgbm_model.py
```

Start prediction API:

```bash
python prediction_service.py
```

Prediction service endpoints include:

- `/health`
- `/predict/next-race`
- `/predict/full`

### 5) Live Timing Service Setup (live_service)

Install deps:

```bash
cd live_service
pip install -r requirements.txt
```

Run in mock mode (default):

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Run in live mode (official feed):

```bash
F1_MODE=live uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Useful env vars:

- `F1_MODE=mock|live`
- `TRACK_NAME=Melbourne` (mock track)
- `TRACK_DATA_DIR=/path/to/TrackCoordinateJS`

### 6) Data Pipeline Setup (data_pipeline)

Install deps:

```bash
cd data_pipeline
pip install -r requirements.txt
```

Run orchestrator from project root:

```bash
cd ..
python -m data_pipeline.orchestrator
```

## Common Run Combinations

### Frontend + Backend + Prediction API

Terminal 1:

```bash
cd backend
./mvnw spring-boot:run
```

Terminal 2:

```bash
cd Data/Simulation
python prediction_service.py
```

Terminal 3:

```bash
cd frontend
npm run dev
```

### Frontend + Backend + Live Timing (Mock)

Terminal 1:

```bash
cd backend
./mvnw spring-boot:run
```

Terminal 2:

```bash
cd live_service
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Terminal 3:

```bash
cd frontend
npm run dev
```

## Track Coordinate Asset Commands

Convert all CSV tracks to JS assets:

```bash
cd frontend/public/circuit_3d
python csv_reading.py
```

Generate missing track CSVs from FastF1:

```bash
cd frontend/public/circuit_3d
python generate_missing_track_csvs_fastf1.py
```

Compare generated Melbourne variant against current baseline:

```bash
cd frontend/public/circuit_3d
python compare_melbourne_fastf1.py
```

## Testing and Build Commands

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

- Supabase credentials are required for data pipeline ingestion and some backend circuit/session endpoints.
- If you see connection failures from backend prediction endpoints, ensure `Data/Simulation/prediction_service.py` is running on port `8000`.
- If you use `live_service` on a different port, update `frontend/vite.config.ts` proxy and any backend hardcoded URLs as needed.
  `
