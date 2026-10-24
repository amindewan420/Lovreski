// Admin Panel API client — uses a separate admin JWT (never the user token).
import axios from "axios";
import { API_BASE } from "@/lib/api";

const KEY = "lovreski_admin_token";

export const getAdminToken = () => localStorage.getItem(KEY);
export const setAdminToken = (t) => (t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY));

export const adminApi = axios.create({ baseURL: API_BASE });

adminApi.interceptors.request.use((config) => {
  const t = getAdminToken();
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

// Token revoked/invalid while using the panel → back to login.
adminApi.interceptors.response.use(
  (r) => r,
  (err) => {
    const url = err.config?.url || "";
    if (err.response?.status === 401 && !url.includes("/admin/login") && !url.includes("/admin/verify-token")) {
      setAdminToken(null);
      if (window.location.pathname !== "/admin/login") window.location.replace("/admin/login");
    }
    return Promise.reject(err);
  }
);

// Returns true/false; network errors keep the stored token (offline ≠ logged out).
export async function verifyAdminToken() {
  if (!getAdminToken()) return false;
  try {
    await adminApi.get("/admin/verify-token");
    return true;
  } catch (e) {
    if (e.response && [401, 403].includes(e.response.status)) { setAdminToken(null); return false; }
    return !e.response;
  }
}

export async function adminLogout() {
  const deviceToken = localStorage.getItem("lovreski_admin_fcm_token");
  if (deviceToken) {
    try { await adminApi.delete("/admin/push/token", { data: { token: deviceToken } }); } catch { /* noop */ }
    localStorage.removeItem("lovreski_admin_fcm_token");
  }
  try { await adminApi.post("/admin/logout"); } catch { /* token cleared regardless */ }
  setAdminToken(null);
}
