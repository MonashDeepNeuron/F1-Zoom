import { useState, useEffect } from "react";
import { Carousel } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { getPrediction, getLastRace } from '../services/api';
import ParticleDriver from './ParticleDriver';
import "../styles/PredictionCarousel.css";

function PredictionCarousel() {
    const [nextRacePrediction, setNextRacePrediction] = useState<any>(null);
    const [lastRaceWinner, setLastRaceWinner] = useState<any>(null);

    useEffect( () => {
        // Fetch next race prediction from model 
        getPrediction()
            .then(res => setNextRacePrediction(res.data))
            .catch(err => console.error('Error fetching prediciton:', err));

        // Fetch last race winner
        getLastRace()
            .then(res => {
                const races = res.data.MRData?.RaceTable?.Races || [];
                if (races.length > 0) {
                    const lastRace = races[0];
                    const winner = lastRace.Results?.[0];
                    setLastRaceWinner({ race: lastRace, winner})
                }
            })
            .catch(err => console.error('Error fetching last race:', err));
}, []);

return (
    <div className="prediction-carousel-container">
        <Carousel>
            {/* Slide 1: Next Race Prediction */}
            <Carousel.Item>
                <div className="carousel-card">
                    <div className="carousel-left">
                        <ParticleDriver />
                    </div>
                    <div className="carousel-right">
                        <h2>Next Race Prediction</h2>
                        {nextRacePrediction ? (
                            <>
                                <h3>{nextRacePrediction.predictedWinner || 'TBD'}</h3>
                                <p>Confidence: {nextRacePrediction.confidence || 'N/A'}</p>
                                <p className="status">{nextRacePrediction.status}</p>
                                <Link to="/predictions" className="view-full-button">
                                    View Full Predictions &rarr;
                                </Link>
                            </>
                        ): (<p>Loading prediction...</p>
                        )}
                    </div>
                </div>
            </Carousel.Item>

            {/* Slide 2: Last Race Winner */}
            <Carousel.Item>
                <div className="carousel-card">
                    <div className="carousel-left">
                        <ParticleDriver />
                    </div>
                    <div className="carousel-right">
                        <h2>Last Race Winner</h2>
                        {lastRaceWinner ? (
                            <>
                                <h3>
                                {lastRaceWinner.winner?.Driver?.givenName}{' '}
                                {lastRaceWinner.winner?.Driver?.familyName}
                                </h3>
                                <p>Race: {lastRaceWinner.race?.raceName}</p>
                                <p>Team: {lastRaceWinner.winner?.Constructor?.name}</p>
                            </>
                            ) : (
                            <p>Loading last race winner...</p>
                            )}
                    </div>
                </div> 
            </Carousel.Item>       
        </Carousel>
    </div>
);

}
export default PredictionCarousel;