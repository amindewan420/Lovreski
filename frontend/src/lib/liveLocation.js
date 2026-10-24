// Live-location sender: keeps pushing the device position for an active share
// until its 5-minute window ends. Lives outside React so it survives navigation.
import { api } from "@/lib/api";

const shares = new Map(); // message_id -> { watchId, timer, last, lastSent }
const listeners = new Set();
const emit = () => listeners.forEach((fn) => fn());

export const subscribeLive = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };
export const isLiveActive = (mid) => shares.has(mid);

const MIN_INTERVAL_MS = 8000;

export function stopLiveShare(mid, { notify = true } = {}) {
  const s = shares.get(mid);
  if (!s) return;
  if (s.watchId != null) navigator.geolocation?.clearWatch(s.watchId);
  clearTimeout(s.timer);
  shares.delete(mid);
  if (notify) api.post(`/location/${mid}/stop`).catch(() => {});
  emit();
}

export function startLiveShare(mid, expiresAt) {
  if (!navigator.geolocation || shares.has(mid)) return;
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (ms <= 0) return;
  const s = { watchId: null, timer: null, lastSent: 0 };
  s.timer = setTimeout(() => stopLiveShare(mid, { notify: false }), ms);
  s.watchId = navigator.geolocation.watchPosition(
    (p) => {
      if (Date.now() - s.lastSent < MIN_INTERVAL_MS) return;
      s.lastSent = Date.now();
      api.post(`/location/${mid}/update`, { lat: p.coords.latitude, lng: p.coords.longitude })
        .catch((e) => { if (e.response?.status === 410 || e.response?.status === 404) stopLiveShare(mid, { notify: false }); });
    },
    () => {},
    { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 }
  );
  shares.set(mid, s);
  emit();
}

export const getCurrentPosition = (timeout = 10000) => new Promise((res, rej) => {
  if (!navigator.geolocation) return rej(new Error("unsupported"));
  navigator.geolocation.getCurrentPosition((p) => res([p.coords.latitude, p.coords.longitude]), rej,
    { enableHighAccuracy: true, timeout, maximumAge: 30000 });
});

export const distanceKm = ([a1, o1], [a2, o2]) => {
  const R = 6371, r = Math.PI / 180;
  const dLat = (a2 - a1) * r, dLng = (o2 - o1) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a1 * r) * Math.cos(a2 * r) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
};

export const fmtDistance = (km) => (km < 1 ? `${Math.round(km * 1000)} м` : `${km.toFixed(km < 10 ? 1 : 0)} км`);

export const googleMapsUrl = (lat, lng, origin) =>
  `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}${origin ? `&origin=${origin[0]},${origin[1]}` : ""}`;
