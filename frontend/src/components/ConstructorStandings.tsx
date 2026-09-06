import { useState, useEffect } from "react";
import { Card } from "react-bootstrap";
import { getConstructorStandings } from "../services/api";
import "../styles/Standings.css";

function ConstructorStandings() {
  const [constructors, setConstructors] = useState<any[]>([]);

  useEffect(() => {
    getConstructorStandings()
      .then((res) => {
        const standings =
          res.data.MRData?.StandingsTable?.StandingsLists[0]
            ?.ConstructorStandings || [];
        setConstructors(standings.slice(0, 5)); // Top 5
      })
      .catch((err) =>
        console.error("Error fetching constructor standings:", err)
      );
  }, []);

  return (
    <Card className="standings-card">
      <Card.Header>
        <h3> Constructor Standings</h3>
      </Card.Header>
      <Card.Body>
        {constructors.length > 0 ? (
          <ul className="standings-list">
            {constructors.map((standing: any) => (
              <li key={standing.position}>
                <span className="position">{standing.position}.</span>
                <span className="team-name">{standing.Constructor.name}</span>
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

export default ConstructorStandings;
