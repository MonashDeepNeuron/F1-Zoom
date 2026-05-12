import { useEffect, useState } from "react";
import { getCircuitsBySeason, getNextRace } from "../services/api";

export interface NextRaceCircuit {
  status: "loading" | "ready" | "error";
  /** File slug matching `/circuit_3d/TrackCoordinateJS/<slug>.js` (also the
   *  key in `CIRCUIT_THEME`). Null while loading or if no match was found. */
  circuitName: string | null;
  /** Track length in km from the circuits endpoint, used to size the
   *  cinematic projection. */
  lengthKm: number | null;
  /** Round number from the circuits endpoint (handy for analytics). */
  round: number | null;
  /** Human-readable error if `status === "error"`. */
  error: string | null;
}

interface NextRaceApiRace {
  raceName?: string;
  round?: string;
  date?: string;
  Circuit?: {
    circuitId?: string;
    circuitName?: string;
    Location?: { locality?: string; country?: string };
  };
}

interface CircuitApiRow {
  code: string;
  fileSlug: string;
  title: string;
  subtitle: string;
  flag: string;
  lengthKm: number;
  round?: number | null;
  grandPrixName?: string | null;
}

interface CircuitMatch {
  fileSlug: string;
  code: string;
  title: string;
  subtitle: string;
  lengthKm: number;
  round: number | null;
  grandPrixName: string | null;
}

const DEFAULT_SEASON = new Date().getFullYear();
const INITIAL_STATE: NextRaceCircuit = {
  status: "loading",
  circuitName: null,
  lengthKm: null,
  round: null,
  error: null,
};

function normalizeForMatch(value?: string | null): string {
  if (!value) return "";
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function mapRow(row: CircuitApiRow): CircuitMatch {
  return {
    fileSlug: row.fileSlug,
    code: row.code,
    title: row.title,
    subtitle: row.subtitle,
    lengthKm: row.lengthKm,
    round: row.round ?? null,
    grandPrixName: row.grandPrixName ?? null,
  };
}

/**
 * Mirrors CircuitHero's `pickInitialTrack` heuristic: match by GP name,
 * circuit name, circuit id / locality, and finally fall back to round
 * number, then the first track in the season.
 */
function pickCircuit(
  tracks: CircuitMatch[],
  nextRace: NextRaceApiRace | null,
): CircuitMatch | null {
  if (tracks.length === 0) return null;
  if (!nextRace) return tracks[0];

  const raceNameNorm = normalizeForMatch(nextRace.raceName);
  const circuitNameNorm = normalizeForMatch(nextRace.Circuit?.circuitName);
  const circuitIdNorm = normalizeForMatch(nextRace.Circuit?.circuitId);
  const localityNorm = normalizeForMatch(nextRace.Circuit?.Location?.locality);

  const byName = tracks.find((track) => {
    const titleNorm = normalizeForMatch(track.title);
    const gpNameNorm = normalizeForMatch(track.grandPrixName);
    const codeNorm = normalizeForMatch(track.code);
    const subtitleNorm = normalizeForMatch(track.subtitle);

    return (
      (raceNameNorm &&
        (gpNameNorm === raceNameNorm ||
          titleNorm.includes(raceNameNorm) ||
          raceNameNorm.includes(gpNameNorm))) ||
      (circuitNameNorm && subtitleNorm.includes(circuitNameNorm)) ||
      (circuitIdNorm &&
        (codeNorm === circuitIdNorm ||
          titleNorm.includes(circuitIdNorm) ||
          subtitleNorm.includes(circuitIdNorm))) ||
      (localityNorm &&
        (titleNorm.includes(localityNorm) ||
          subtitleNorm.includes(localityNorm)))
    );
  });
  if (byName) return byName;

  const nextRound = Number(nextRace.round);
  if (Number.isFinite(nextRound)) {
    const byRound = tracks.find((track) => track.round === nextRound);
    if (byRound) return byRound;
  }

  return tracks[0];
}

function describeError(error: unknown): string {
  if (typeof error !== "object" || error === null) {
    return "Unable to resolve next race.";
  }
  const maybeAxios = error as {
    response?: { data?: unknown };
    message?: string;
  };
  if (typeof maybeAxios.response?.data === "string") {
    return maybeAxios.response.data;
  }
  if (
    typeof maybeAxios.response?.data === "object" &&
    maybeAxios.response.data !== null &&
    "message" in (maybeAxios.response.data as Record<string, unknown>) &&
    typeof (maybeAxios.response.data as Record<string, unknown>).message ===
      "string"
  ) {
    return (maybeAxios.response.data as Record<string, string>).message;
  }
  return maybeAxios.message ?? "Unable to resolve next race.";
}

/**
 * Resolves which circuit the upcoming race is at by combining the
 * `/races/next` endpoint with `/circuits/season/:year`. Returns the file
 * slug (matching `public/circuit_3d/TrackCoordinateJS/<slug>.js`) plus
 * `lengthKm`, both directly consumable by `<LandingIntro>`.
 */
export function useNextRaceCircuit(): NextRaceCircuit {
  const [state, setState] = useState<NextRaceCircuit>(INITIAL_STATE);

  useEffect(() => {
    let active = true;

    getNextRace()
      .catch(() => null)
      .then((nextRaceRes) => {
        const nextRace: NextRaceApiRace | null =
          nextRaceRes?.data?.MRData?.RaceTable?.Races?.[0] ?? null;
        const seasonFromDate = nextRace?.date
          ? new Date(nextRace.date).getUTCFullYear()
          : NaN;
        const seasonToLoad = Number.isFinite(seasonFromDate)
          ? seasonFromDate
          : DEFAULT_SEASON;

        return getCircuitsBySeason(seasonToLoad).then((circuitsRes) => ({
          circuitsRes,
          nextRace,
        }));
      })
      .then(({ circuitsRes, nextRace }) => {
        if (!active) return;
        const rows: CircuitApiRow[] = Array.isArray(circuitsRes.data)
          ? circuitsRes.data
          : [];
        const tracks = rows
          .map(mapRow)
          .sort((a, b) => (a.round ?? 999) - (b.round ?? 999));

        const match = pickCircuit(tracks, nextRace);
        if (!match) {
          setState({
            status: "error",
            circuitName: null,
            lengthKm: null,
            round: null,
            error: "No circuits found in database.",
          });
          return;
        }

        setState({
          status: "ready",
          circuitName: match.fileSlug,
          lengthKm: Number.isFinite(match.lengthKm) ? match.lengthKm : null,
          round: match.round,
          error: null,
        });
      })
      .catch((err: unknown) => {
        if (!active) return;
        console.error("[useNextRaceCircuit] failed", err);
        setState({
          status: "error",
          circuitName: null,
          lengthKm: null,
          round: null,
          error: describeError(err),
        });
      });

    return () => {
      active = false;
    };
  }, []);

  return state;
}
