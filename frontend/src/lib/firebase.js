// Firebase Web SDK client — config is fetched at runtime from the backend
// (configured by the admin in the Admin Panel), not from build-time env vars.
import { initializeApp, getApps, deleteApp } from "firebase/app";
import { getMessaging, isSupported } from "firebase/messaging";
import { api } from "@/lib/api";

let _cfgPromise = null;
let _app = null;
let _appKey = null;

export function loadPushConfig(force = false) {
  if (!_cfgPromise || force) {
    _cfgPromise = api.get("/push/config").then((r) => r.data).catch(() => ({ configured: false }));
  }
  return _cfgPromise;
}

export function toFirebaseOptions(cfg) {
  return {
    apiKey: cfg.apiKey, authDomain: cfg.authDomain, projectId: cfg.projectId,
    messagingSenderId: cfg.messagingSenderId, appId: cfg.appId,
  };
}

async function getFirebaseApp() {
  const cfg = await loadPushConfig();
  if (!cfg?.configured) return null;
  const key = JSON.stringify(toFirebaseOptions(cfg));
  if (_app && _appKey === key) return _app;
  if (_app) { try { await deleteApp(_app); } catch { /* noop */ } }
  const existing = getApps()[0];
  if (existing) { try { await deleteApp(existing); } catch { /* noop */ } }
  _app = initializeApp(toFirebaseOptions(cfg));
  _appKey = key;
  return _app;
}

export async function getBrowserMessaging() {
  try {
    if (!(await isSupported())) return null;
    const app = await getFirebaseApp();
    return app ? getMessaging(app) : null;
  } catch (e) {
    console.warn("[fcm] getMessaging unsupported:", e);
    return null;
  }
}
