import axios from "axios";

const API_BASE =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8080/api/v1";

export const getDriverStandings = () =>
  axios.get(`${API_BASE}/championship/drivers`);

export const getConstructorStandings = () =>
  axios.get(`${API_BASE}/championship/constructors`);

export const getNextRace = () => axios.get(`${API_BASE}/races/next`);

export const getLastRace = () => axios.get(`${API_BASE}/races/last`);

export const getRaceSchedule = () => axios.get(`${API_BASE}/races/schedule`);

export const getRaceCalendar = () => axios.get(`${API_BASE}/races/calendar`);

export const getCircuitsBySeason = (season: number) =>
  axios.get(`${API_BASE}/circuits/season/${season}`);

export const getPrediction = () =>
  axios.get(`${API_BASE}/predictions/next-race`);
