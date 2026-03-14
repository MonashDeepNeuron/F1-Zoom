import { useState, useEffect } from "react";
import { Container, Row, Col, Card } from "react-bootstrap";
import { Link } from "react-router-dom";
import { getFullPrediction } from "../services/api";
import "../styles/Predictions.css";

interface Driver {
  position: number;
  driver: string;
  team: string | null;
  gridPosition: number;
  score: number;
}

interface PredictionData {
  status: string;
  predictedWinner: string;
  winnerTeam: string | null;
  confidence: string;
  scoreGap: number;
  top10: Driver[];
  raceName: string;
  season: number;
}

function Predictions() {
  const [prediction, setPrediction] = useState<PredictionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getFullPrediction()
      .then((res) => {
        setPrediction(res.data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Error fetching predictions:", err);
        setError("Failed to load predictions");
        setLoading(false);
      });
  }, []);

  const getPositionColor = (position: number) => {
    if (position === 1) return "#ffd700"; // Gold
    if (position === 2) return "#c0c0c0"; // Silver
    if (position === 3) return "#cd7f32"; // Bronze
    if (position <= 10) return "#00ff00"; // Green (points)
    return "#888"; // Gray
  };

  const getScoreBarWidth = (score: number, maxScore: number) => {
    if (maxScore <= 0) return "0%";
    const normalized = ((score - -25) / (maxScore - -25)) * 100;
    return `${Math.max(0, Math.min(100, normalized))}%`;
  };

  return (
    <div className="predictions-page">
      {/* Header */}
      <header className="predictions-header">
        <Container>
          <Link to="/" className="back-button">
            &larr; Back to Home
          </Link>
          <h1 className="predictions-title">Race Prediction Results</h1>
          <p className="predictions-subtitle">
            LightGBM Machine Learning Model
          </p>
        </Container>
      </header>

      {/* Main Content */}
      <div className="predictions-content">
        <Container>
          {loading && (
            <div className="loading-state">
              <div className="spinner"></div>
              <p>Loading predictions...</p>
            </div>
          )}

          {error && (
            <div className="error-state">
              <p>{error}</p>
            </div>
          )}

          {prediction && !loading && (
            <>
              {/* Race Info Card */}
              <Card className="race-info-card">
                <Card.Body>
                  <Row className="align-items-center">
                    <Col md={4}>
                      <h3 className="race-name">{prediction.raceName}</h3>
                      <p className="race-season">Season {prediction.season}</p>
                    </Col>
                    <Col md={4} className="text-center">
                      <div className="winner-box">
                        <span className="winner-label">Predicted Winner</span>
                        <h2 className="winner-name">
                          {prediction.predictedWinner}
                        </h2>
                        {prediction.winnerTeam && (
                          <p className="winner-team">{prediction.winnerTeam}</p>
                        )}
                      </div>
                    </Col>
                    <Col md={4} className="text-end">
                      <div className="confidence-box">
                        <span className="confidence-label">Confidence</span>
                        <h2 className="confidence-value">
                          {prediction.confidence}
                        </h2>
                        <p className="score-gap">
                          Score Gap: {prediction.scoreGap.toFixed(2)}
                        </p>
                      </div>
                    </Col>
                  </Row>
                </Card.Body>
              </Card>

              {/* Full Grid Prediction */}
              <div className="grid-prediction">
                <h2 className="section-title">Complete Grid Prediction</h2>

                <div className="drivers-grid">
                  {prediction.top10.map((driver) => {
                    const maxScore = prediction.top10[0]?.score || 20;

                    return (
                      <Card key={driver.position} className="driver-card">
                        <Card.Body>
                          <Row className="align-items-center">
                            {/* Position */}
                            <Col xs={2} className="position-col">
                              <div
                                className="position-badge"
                                style={{
                                  borderColor: getPositionColor(driver.position)
                                }}
                              >
                                P{driver.position}
                              </div>
                            </Col>

                            {/* Driver Info */}
                            <Col xs={4}>
                              <h3 className="driver-name">{driver.driver}</h3>
                              {driver.team && (
                                <p className="driver-team">{driver.team}</p>
                              )}
                            </Col>

                            {/* Grid Position */}
                            <Col xs={2} className="text-center">
                              <div className="grid-badge">
                                <span className="grid-label">Grid</span>
                                <span className="grid-value">
                                  P{driver.gridPosition || "?"}
                                </span>
                              </div>
                            </Col>

                            {/* Score Bar */}
                            <Col xs={4}>
                              <div className="score-container">
                                <div className="score-bar-bg">
                                  <div
                                    className="score-bar-fill"
                                    style={{
                                      width: getScoreBarWidth(
                                        driver.score,
                                        maxScore
                                      ),
                                      backgroundColor:
                                        driver.score > 0
                                          ? "#ff0000"
                                          : "rgba(255, 255, 255, 0.2)"
                                    }}
                                  ></div>
                                </div>
                                <span className="score-value">
                                  {driver.score.toFixed(2)}
                                </span>
                              </div>
                            </Col>
                          </Row>
                        </Card.Body>
                      </Card>
                    );
                  })}
                </div>
              </div>

              {/* Model Info */}
              <Card className="model-info-card">
                <Card.Body>
                  <h3 className="model-title">About the Model</h3>
                  <p className="model-description">
                    Predictions generated using LightGBM Ranker with 2000
                    estimators, trained on historical F1 race data including
                    qualifying performance, driver history, track
                    characteristics, and pace analysis. The model uses 46
                    features including grid position, qualifying times,
                    historical performance metrics, and track-specific data.
                  </p>
                  <div className="model-stats">
                    <div className="stat-item">
                      <span className="stat-label">Status</span>
                      <span className="stat-value">{prediction.status}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">Top Features</span>
                      <span className="stat-value">
                        Position Gain, Grid Position, Pace Score
                      </span>
                    </div>
                  </div>
                </Card.Body>
              </Card>
            </>
          )}
        </Container>
      </div>
    </div>
  );
}

export default Predictions;
