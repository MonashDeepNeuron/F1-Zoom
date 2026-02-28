import { useState, useEffect, useMemo } from "react";
import { Card } from "react-bootstrap";
import { getNextRace } from "../services/api";
import "../styles/NextRaceInfo.css";

interface NextRaceInfoProps {
  showCountdown?: boolean;
}

function NextRaceInfo({ showCountdown = false }: NextRaceInfoProps) {
  const [nextRace, setNextRace] = useState<any>(null);
  const [now, setNow] = useState<Date>(new Date());

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

  useEffect(() => {
    if (!showCountdown) return;
    const id = window.setInterval(() => {
      setNow(new Date());
    }, 1000);
    return () => window.clearInterval(id);
  }, [showCountdown]);

  const raceStart = useMemo(() => {
    if (!nextRace?.date) return null;
    const date: string = nextRace.date;
    const time: string = nextRace.time || "00:00:00Z";
    return new Date(`${date}T${time}`);
  }, [nextRace]);

  let countdown:
    | {
        days: number;
        hours: number;
        minutes: number;
        seconds: number;
      }
    | null = null;
  let hasStartedOrPassed = false;

  if (showCountdown && raceStart) {
    const diffMs = raceStart.getTime() - now.getTime();
    if (diffMs > 0) {
      const totalSeconds = Math.floor(diffMs / 1000);
      const days = Math.floor(totalSeconds / 86400);
      const hours = Math.floor((totalSeconds % 86400) / 3600);
      const minutes = Math.floor((totalSeconds % 3600) / 60);
      const seconds = totalSeconds % 60;
      countdown = { days, hours, minutes, seconds };
    } else {
      hasStartedOrPassed = true;
    }
  }

  return (
    <Card className="next-race-card">
      <Card.Header>
        <h3> Next Race</h3>
      </Card.Header>
      <Card.Body>
        {nextRace ? (
          <>
            <h4>{nextRace.raceName}</h4>
            <p>{nextRace.Circuit?.circuitName}</p>
            <p>{nextRace.date}</p>
            <p>{nextRace.time}</p>
            <p className="location">
              {nextRace.Circuit?.Location?.locality},{" "}
              {nextRace.Circuit?.Location?.country}
            </p>
            {showCountdown && (
              <div className="next-race-countdown">
                {raceStart && countdown ? (
                  <>
                    <p className="next-race-countdown-label">Starts in</p>
                    <div className="next-race-countdown-timer">
                      <div className="next-race-countdown-unit">
                        <span className="next-race-countdown-value mono">
                          {countdown.days}
                        </span>
                        <span className="next-race-countdown-unit-label">
                          days
                        </span>
                      </div>
                      <div className="next-race-countdown-unit">
                        <span className="next-race-countdown-value mono">
                          {countdown.hours.toString().padStart(2, "0")}
                        </span>
                        <span className="next-race-countdown-unit-label">
                          hrs
                        </span>
                      </div>
                      <div className="next-race-countdown-unit">
                        <span className="next-race-countdown-value mono">
                          {countdown.minutes.toString().padStart(2, "0")}
                        </span>
                        <span className="next-race-countdown-unit-label">
                          min
                        </span>
                      </div>
                      <div className="next-race-countdown-unit">
                        <span className="next-race-countdown-value mono">
                          {countdown.seconds.toString().padStart(2, "0")}
                        </span>
                        <span className="next-race-countdown-unit-label">
                          sec
                        </span>
                      </div>
                    </div>
                  </>
                ) : showCountdown ? (
                  <p className="next-race-countdown-label">
                    {hasStartedOrPassed
                      ? "Session is starting now or already underway."
                      : "Countdown unavailable."}
                  </p>
                ) : null}
              </div>
            )}
          </>
        ) : (
          <p>Loading next race...</p>
        )}
      </Card.Body>
    </Card>
  );
}

export default NextRaceInfo;
