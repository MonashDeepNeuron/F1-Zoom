import { useEffect, useState } from "react";
import {
  ComposableMap,
  Geographies,
  Geography,
  Marker,
  ZoomableGroup
} from "react-simple-maps";
import { getRaceCalendar } from "../services/api";
import "../styles/RaceCalendarMap.css";

// World map GeoJSON URL (simplified topojson)
const geoUrl = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

interface Race {
  raceName: string;
  Circuit: {
    circuitName: string;
    Location: {
      lat: string;
      long: string;
      locality: string;
      country: string;
    };
  };
  date: string;
  time?: string;
}

interface RaceLocation {
  name: string;
  city: string;
  country: string;
  coordinates: [number, number];
  date: string;
  isNext: boolean;
  round: number;
}

export default function RaceCalendarMap() {
  const defaultCenter: [number, number] = [10, 20];
  const [races, setRaces] = useState<RaceLocation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredRace, setHoveredRace] = useState<RaceLocation | null>(null);
  const [mapCenter, setMapCenter] = useState<[number, number]>(defaultCenter);
  const [mapZoom, setMapZoom] = useState(1);

  useEffect(() => {
    const fetchCalendar = async () => {
      try {
        const response = await getRaceCalendar();
        const raceData = response.data.MRData.RaceTable.Races;

        // Get current date to determine next race
        const today = new Date();
        let nextRaceIndex = -1;

        // Find the next upcoming race
        for (let i = 0; i < raceData.length; i++) {
          const raceDate = new Date(raceData[i].date);
          if (raceDate >= today) {
            nextRaceIndex = i;
            break;
          }
        }

        const locations: RaceLocation[] = raceData.map(
          (race: Race, index: number) => ({
            name: race.raceName,
            city: race.Circuit.Location.locality,
            country: race.Circuit.Location.country,
            coordinates: [
              parseFloat(race.Circuit.Location.long),
              parseFloat(race.Circuit.Location.lat)
            ] as [number, number],
            date: race.date,
            isNext: index === nextRaceIndex,
            round: index + 1
          })
        );

        setRaces(locations);
        const nextRace = locations.find((race) => race.isNext);
        if (nextRace) {
          setMapCenter(nextRace.coordinates);
          setMapZoom(2.2);
        } else {
          setMapCenter(defaultCenter);
          setMapZoom(1);
        }
        setLoading(false);
      } catch (err) {
        console.error("Error fetching race calendar:", err);
        setError("Failed to load race calendar");
        setLoading(false);
      }
    };

    fetchCalendar();
  }, []);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric"
    });
  };

  if (loading) {
    return (
      <div className="race-calendar-container">
        <div className="race-calendar-loading">Loading Race Calendar...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="race-calendar-container">
        <div className="race-calendar-error">{error}</div>
      </div>
    );
  }

  return (
    <div className="race-calendar-container">
      <h2 className="race-calendar-title">2025 F1 RACE CALENDAR</h2>
      <p className="race-calendar-subtitle">
        Track the Formula 1 World Championship across the globe
      </p>

      <div className="race-calendar-map-wrapper">
        <ComposableMap
          projection="geoMercator"
          projectionConfig={{
            scale: 140,
            center: mapCenter
          }}
          className="race-calendar-map"
        >
          <ZoomableGroup
            center={mapCenter}
            zoom={mapZoom}
            minZoom={1}
            maxZoom={4}
            disablePanning
          >
            <Geographies geography={geoUrl}>
              {({ geographies }) =>
                geographies.map((geo) => (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill="#1a0000"
                    stroke="#ff0000"
                    strokeWidth={0.5}
                    style={{
                      default: { outline: "none" },
                      hover: { outline: "none", fill: "#2a0000" },
                      pressed: { outline: "none" }
                    }}
                  />
                ))
              }
            </Geographies>

            {races.map((race) => (
              <Marker
                key={race.round}
                coordinates={race.coordinates}
                onMouseEnter={() => setHoveredRace(race)}
                onMouseLeave={() => setHoveredRace(null)}
              >
                <g className={`race-marker ${race.isNext ? "next-race" : ""}`}>
                  {/* Pin circle */}
                  <circle
                    r={race.isNext ? 8 : 5}
                    fill={race.isNext ? "#ff0000" : "#cc0000"}
                    stroke={race.isNext ? "#ffffff" : "#ff0000"}
                    strokeWidth={race.isNext ? 2 : 1}
                    className="race-pin"
                    style={{
                      cursor: "pointer",
                      filter: race.isNext
                        ? "drop-shadow(0 0 10px rgba(255, 0, 0, 0.8))"
                        : "none"
                    }}
                  />

                  {/* Pulse animation for next race */}
                  {race.isNext && (
                    <circle
                      r={8}
                      fill="none"
                      stroke="#ff0000"
                      strokeWidth={2}
                      opacity={0}
                      className="pulse-ring"
                    />
                  )}

                  {/* Label for next race */}
                  {race.isNext && (
                    <text
                      textAnchor="middle"
                      y={-15}
                      className="race-label next-race-label"
                      style={{
                        fontSize: "10px",
                        fontWeight: "bold",
                        fill: "#ffffff",
                        textShadow: "0 0 10px rgba(255, 0, 0, 0.8)",
                        pointerEvents: "none"
                      }}
                    >
                      NEXT: {race.city}
                    </text>
                  )}
                </g>
              </Marker>
            ))}
          </ZoomableGroup>
        </ComposableMap>

        {/* Tooltip */}
        {hoveredRace && (
          <div className="race-tooltip">
            <div className="race-tooltip-round">Round {hoveredRace.round}</div>
            <div className="race-tooltip-name">{hoveredRace.name}</div>
            <div className="race-tooltip-location">
              {hoveredRace.city}, {hoveredRace.country}
            </div>
            <div className="race-tooltip-date">
              {formatDate(hoveredRace.date)}
            </div>
            {hoveredRace.isNext && (
              <div className="race-tooltip-badge">NEXT RACE</div>
            )}
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="race-calendar-legend">
        <div className="legend-item">
          <div className="legend-pin next-race-pin"></div>
          <span>Next Race</span>
        </div>
        <div className="legend-item">
          <div className="legend-pin regular-pin"></div>
          <span>Upcoming Races</span>
        </div>
        <div className="legend-item">
          <div className="legend-pin past-pin"></div>
          <span>Completed Races</span>
        </div>
      </div>
    </div>
  );
}
