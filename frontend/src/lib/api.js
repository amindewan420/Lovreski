// Central API client for Lovreski.
// Backend URL resolution order:
//   1. REACT_APP_BACKEND_URL       — original / preview environment
//   2. REACT_APP_API_URL           — Amvera deploy spec
//   3. empty string                — same-origin (single-container Docker deploy)
import axios from "axios";

const BACKEND_URL =
  process.env.REACT_APP_BACKEND_URL ||
  process.env.REACT_APP_API_URL ||
  "";
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

// Server-side profile-completion gate → let <ProfileGate/> redirect + explain
api.interceptors.response.use(undefined, (error) => {
  const d = error.response?.data?.detail;
  if (error.response?.status === 403 && d?.code === "profile_incomplete") {
    error.profileGate = true;
    window.dispatchEvent(new CustomEvent("lovreski:profile-incomplete", { detail: d.missing || [] }));
  }
  return Promise.reject(error);
});

export const setToken = (t) => {
  if (t) localStorage.setItem("lovreski_token", t);
  else localStorage.removeItem("lovreski_token");
};

export const getToken = () => localStorage.getItem("lovreski_token");
