import { Row, Col } from "react-bootstrap";
import CircuitHero from "../components/CircuitHero";
import LandingIntro from "../components/LandingIntro";
import PredictionCarousel from "../components/PredictionCarousel";
import DriverStandings from "../components/DriverStandings";
import ConstructorStandings from "../components/ConstructorStandings";
import NextRaceInfo from "../components/NextRaceInfo";
import RaceCalendarMap from "../components/RaceCalendarMap";
import TopNav from "../components/TopNav";
import { useNextRaceCircuit } from "../hooks/useNextRaceCircuit";
import "../styles/Home.css";

const LANDING_INTRO_STORAGE_KEY = "f1zoom:landing-intro";

function Home() {
  // Resolve which circuit the upcoming race is on so the cinematic opens
  // on the right track. Re-uses the same matching heuristic CircuitHero
  // does, so intro and hero always agree on the active circuit.
  const nextRace = useNextRaceCircuit();

  return (
    <div className="home-page">
      <TopNav />
      {/*
        Landing intro overlay (sibling, not wrapper) — sits at z-index 9999
        above CircuitHero. Plays once per device, gated by a single global
        localStorage key (`f1zoom:landing-intro`). To replay while iterating:
          - delete that key from DevTools → Application → Local Storage, or
          - uncomment `forcePlay` below.

        After the cinematic completes the overlay cross-fades into a
        playable pixel mini racing game on the same circuit (`endGame`).
      */}
      {nextRace.status === "ready" && nextRace.circuitName && (
        <LandingIntro
          key={nextRace.circuitName}
          circuitName={nextRace.circuitName}
          trackLengthKm={nextRace.lengthKm}
          durationMs={6000}
          storageKey={LANDING_INTRO_STORAGE_KEY}
          // audioSrc="/audio/engine.mp3"
          endGame
          forcePlay
        />
      )}

      {/* Hero: 3D Circuit Visualization (full viewport) */}
      <CircuitHero />

      {/* Dashboard content (scroll to reveal) */}
      <div className="home-dashboard">
        <h1 className="dashboard-title">Predict The Grid</h1>

        <div className="dashboard-content">
          {/* Top: Horizontal Carousel */}
          <PredictionCarousel />

          {/* Bottom: Three Vertical Cards */}
          <Row className="cards-row">
            <Col md={4}>
              <DriverStandings />
            </Col>
            <Col md={4}>
              <ConstructorStandings />
            </Col>
            <Col md={4}>
              <NextRaceInfo />
            </Col>
          </Row>

          {/* Race Calendar Map */}
          <RaceCalendarMap />
        </div>
      </div>
    </div>
  );
}

export default Home;
