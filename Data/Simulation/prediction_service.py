"""
FastAPI Prediction Service for F1 Race Predictions
Serves LightGBM model predictions via REST API
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import joblib
from pathlib import Path
from typing import Dict, List, Any
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="F1 Race Prediction API",
    description="LightGBM-based race prediction service",
    version="1.0.0"
)

# Enable CORS for Spring Boot backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Model and data paths
BASE_DIR = Path(__file__).parent.resolve()
MODEL_PATH = BASE_DIR / "f1_ranker_model.pkl"
PREDICTIONS_PATH = BASE_DIR / "latest_predictions.csv"

# Global model variable
model = None

@app.on_event("startup")
async def load_model():
    """Load the trained model on startup"""
    global model
    try:
        if MODEL_PATH.exists():
            model = joblib.load(MODEL_PATH)
            logger.info(f"✓ Model loaded from {MODEL_PATH}")
        else:
            logger.warning(f"⚠️  Model file not found at {MODEL_PATH}")
            logger.info("Run lightgbm_model.py first to train and save the model")
    except Exception as e:
        logger.error(f"Error loading model: {e}")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "F1 Prediction API",
        "status": "running",
        "model_loaded": model is not None
    }

@app.get("/health")
async def health():
    """Detailed health check"""
    return {
        "status": "healthy",
        "model_available": model is not None,
        "predictions_available": PREDICTIONS_PATH.exists()
    }

@app.get("/predict/next-race")
async def predict_next_race() -> Dict[str, Any]:
    """
    Get predictions for the next race
    Returns the full prediction results including top 10
    """
    try:
        # Check if we have cached predictions
        if PREDICTIONS_PATH.exists():
            predictions_df = pd.read_csv(PREDICTIONS_PATH)
            
            if len(predictions_df) == 0:
                raise HTTPException(status_code=404, detail="No predictions available")
            
            # Get winner (first row)
            winner = predictions_df.iloc[0]
            
            # Get top 10
            top10 = []
            for _, row in predictions_df.head(10).iterrows():
                top10.append({
                    "position": int(row["predicted_position"]),
                    "driver": row["driver"],
                    "team": row["team"] if pd.notna(row["team"]) else None,
                    "gridPosition": int(row["grid_pos"]) if pd.notna(row["grid_pos"]) else None,
                    "score": round(float(row["prediction_score"]), 2)
                })
            
            # Calculate confidence based on score gap
            winner_score = float(winner["prediction_score"])
            second_score = float(predictions_df.iloc[1]["prediction_score"])
            score_gap = winner_score - second_score
            
            # Map score gap to confidence percentage
            if score_gap > 10:
                confidence = "95%"
            elif score_gap > 7:
                confidence = "90%"
            elif score_gap > 5:
                confidence = "85%"
            elif score_gap > 3:
                confidence = "75%"
            else:
                confidence = "65%"
            
            return {
                "status": "model_ready",
                "predictedWinner": winner["driver"],
                "winnerTeam": winner["team"] if pd.notna(winner["team"]) else None,
                "confidence": confidence,
                "scoreGap": round(score_gap, 2),
                "top10": top10,
                "raceName": predictions_df.iloc[0].get("race_name", "Next Race"),
                "season": int(predictions_df.iloc[0].get("season", 2025))
            }
        
        else:
            # No predictions available yet
            return {
                "status": "no_predictions",
                "predictedWinner": "TBD",
                "confidence": "N/A",
                "message": "Run the model to generate predictions"
            }
            
    except Exception as e:
        logger.error(f"Error getting predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/predict/full")
async def get_full_predictions() -> Dict[str, Any]:
    """Get all 20 drivers' predictions"""
    try:
        if not PREDICTIONS_PATH.exists():
            raise HTTPException(status_code=404, detail="No predictions file found")
        
        predictions_df = pd.read_csv(PREDICTIONS_PATH)
        
        predictions_list = []
        for _, row in predictions_df.iterrows():
            predictions_list.append({
                "position": int(row["predicted_position"]),
                "driver": row["driver"],
                "team": row["team"] if pd.notna(row["team"]) else None,
                "gridPosition": int(row["grid_pos"]) if pd.notna(row["grid_pos"]) else None,
                "score": round(float(row["prediction_score"]), 2)
            })
        
        return {
            "status": "success",
            "predictions": predictions_list,
            "count": len(predictions_list)
        }
        
    except Exception as e:
        logger.error(f"Error getting full predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting F1 Prediction Service...")
    logger.info("API docs available at http://localhost:8000/docs")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
