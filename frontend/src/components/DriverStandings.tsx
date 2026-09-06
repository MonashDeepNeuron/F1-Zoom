import { useState, useEffect } from "react";
import { Card } from "react-bootstrap";
import { getDriverStandings } from "../services/api";
import "../styles/Standings.css";

function DriverStandings() {
  const [drivers, setDrivers] = useState<any[]>([]);

  useEffect(() => {
    getDriverStandings()
      .then((res) => {
        const standings =
          res.data.MRData?.StandingsTable?.StandingsLists[0]?.DriverStandings ||
          [];
        setDrivers(standings.slice(0, 5)); // Top 5
      })
      .catch((err) => console.error("Error fetching driver standings:", err));
  }, []);

  return (
    <Card className="standings-card">
      <Card.Header>
        <h3> Driver Standings</h3>
      </Card.Header>
      <Card.Body>
        {drivers.length > 0 ? (
          <ul className="standings-list">
            {drivers.map((standing: any) => (
              <li key={standing.position}>
                <span className="position">{standing.position}.</span>
                <span className="driver-name">
                  {standing.Driver.givenName} {standing.Driver.familyName}
                </span>
                <span className="points">{standing.points} pts</span>
              </li>
            ))}
          </ul>
        ) : (
          <p>Loading standings...</p>
        )}
      </Card.Body>
    </Card>
  );
}

export default DriverStandings;
