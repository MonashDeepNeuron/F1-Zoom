import { useState, useEffect } from "react";
import { Card } from "react-bootstrap";
import { getNextRace } from "../services/api";
import "../styles/NextRaceInfo.css";

function NextRaceInfo() {
  const [nextRace, setNextRace] = useState<any>(null);

  useEffect(() => {
    getNextRace()
      .then((res) => {
        const races = res.data.MRData?.RaceTable?.Races || [];
        if (races.length > 0) {
          setNextRace(races[0]);
        }
      })
      .catch((err) => console.error("Error fetching next race:", err));
  }, []);

  return (
    <Card className="next-race-card">
      <Card.Header>
        <h3> Next Race</h3>
      </Card.Header>
      <Card.Body>
        {nextRace ? (
          <>
            <h4>{nextRace.raceName}</h4>
            <p> {nextRace.Circuit?.circuitName}</p>
            <p> {nextRace.date}</p>
            <p> {nextRace.time}</p>
            <p className="location">
              {nextRace.Circuit?.Location?.locality},{" "}
              {nextRace.Circuit?.Location?.country}
            </p>
          </>
        ) : (
          <p>Loading next race...</p>
        )}
      </Card.Body>
    </Card>
  );
}

export default NextRaceInfo;
