// Central API client for Lovreski
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});

// Attach token from localStorage on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("lovreski_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const setToken = (t) => {
  if (t) localStorage.setItem("lovreski_token", t);
  else localStorage.removeItem("lovreski_token");
};

export const getToken = () => localStorage.getItem("lovreski_token");
