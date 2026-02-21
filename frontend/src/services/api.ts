import axios from 'axios';

const API_BASE = 'http://localhost:8080/api/v1';

export const getDriverStandings = () =>
    axios.get(`${API_BASE}/championship/drivers`);

export const getConstructorStandings = () =>
    axios.get(`${API_BASE}/championship/constructors`)

export const getNextRace = () =>
    axios.get(`${API_BASE}/races/next`)

export const getLastRace = () =>
    axios.get(`${API_BASE}/races/last`)

export const getRaceCalendar = () =>
    axios.get(`${API_BASE}/races/calendar`)

export const getPrediction = () => 
  axios.get(`${API_BASE}/predictions/next-race`);