import { Row, Col } from 'react-bootstrap';
import CircuitHero from '../components/CircuitHero';
import PredictionCarousel from '../components/PredictionCarousel';
import DriverStandings from '../components/DriverStandings';
import ConstructorStandings from '../components/ConstructorStandings';
import NextRaceInfo from '../components/NextRaceInfo';
import '../styles/Home.css';

function Home() {
  return (
    <div className="home-page">
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
        </div>
      </div>
    </div>
  );
}

export default Home;