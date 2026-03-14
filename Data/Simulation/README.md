# F1 Race Prediction Service

FastAPI-based microservice for serving LightGBM race predictions.

## Architecture

```
Frontend (React) 
    ↓
Spring Boot Backend (Port 8080)
    ↓ 
FastAPI Python Service (Port 8000)
    ↓
LightGBM Model
```

## Setup

### 1. Install Python Dependencies

```bash
conda activate f1-project
pip install -r requirements.txt
```

### 2. Train the Model (First Time Only)

```bash
python lightgbm_model.py
```

This will:
- Train the model on historical data
- Save `f1_ranker_model.pkl` (trained model)
- Save `latest_predictions.csv` (current predictions)

### 3. Start the Prediction Service

```bash
python prediction_service.py
```

The service will start on `http://localhost:8000`

### 4. Verify It's Running

Open your browser and go to:
- http://localhost:8000 (health check)
- http://localhost:8000/docs (interactive API docs)
- http://localhost:8000/predict/next-race (prediction endpoint)

## API Endpoints

### `GET /predict/next-race`

Returns predictions for the next race including predicted winner and top 10.

**Response:**
```json
{
  "status": "model_ready",
  "predictedWinner": "VER",
  "winnerTeam": "Red Bull Racing",
  "confidence": "90%",
  "scoreGap": 6.83,
  "top10": [
    {
      "position": 1,
      "driver": "VER",
      "team": "Red Bull Racing",
      "gridPosition": 1,
      "score": 15.78
    },
    ...
  ],
  "raceName": "Yas Marina Circuit",
  "season": 2025
}
```

### `GET /predict/full`

Returns full predictions for all 20 drivers.

### `GET /health`

Health check endpoint.

## Usage in Production

### Re-train Model (Weekly or After Each Race)

```bash
# Update the race to predict in lightgbm_model.py:
# PRED_SEASON = 2025
# PRED_RACE_NAME = "Monaco"

python lightgbm_model.py
```

The prediction service will automatically use the new predictions.

### Keep Service Running

For production, use a process manager like `systemd` or `supervisord`:

```bash
# Using screen (simple option)
screen -S f1-predictions
python prediction_service.py
# Ctrl+A then D to detach
```

Or use `uvicorn` directly with more options:

```bash
uvicorn prediction_service:app --host 0.0.0.0 --port 8000 --reload
```

## Testing

Test the full stack:

1. Start FastAPI service: `python prediction_service.py`
2. Start Spring Boot: `./mvnw spring-boot:run` (in backend/f1-zoom)
3. Start Frontend: `npm run dev` (in frontend)
4. Navigate to http://localhost:5173 and check the prediction carousel

## Troubleshooting

### "Service Unavailable" Error

Make sure the FastAPI service is running on port 8000:
```bash
curl http://localhost:8000/health
```

### "No Predictions" Response

Train the model first:
```bash
python lightgbm_model.py
```

### Port Already in Use

Kill the process using port 8000:
```bash
lsof -ti:8000 | xargs kill -9
```

## File Structure

```
Data/Simulation/
├── lightgbm_model.py          # Model training script
├── prediction_service.py      # FastAPI service
├── requirements.txt           # Python dependencies
├── f1_ranker_model.pkl        # Trained model (generated)
├── latest_predictions.csv     # Current predictions (generated)
└── README.md                  # This file
```
