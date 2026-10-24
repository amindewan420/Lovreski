// Push notifications hook — FCM Web Push subscribe/unsubscribe + silent token sync.
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { adminApi } from "@/lib/adminApi";
import { loadPushConfig, toFirebaseOptions, getBrowserMessaging } from "@/lib/firebase";
import { getToken, deleteToken } from "firebase/messaging";

const TOKEN_KEY = "lovreski_fcm_token";
export const ADMIN_TOKEN_KEY = "lovreski_admin_fcm_token";
const b64 = (obj) => btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(obj))));

export const pushSupported = () =>
  typeof window !== "undefined" && "serviceWorker" in navigator && "Notification" in window && "PushManager" in window;

export const isIOSNonStandalone = () => {
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
  const standalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
  return isIOS && !standalone;
};

// Registers the SW and fetches/saves the FCM token. Requires permission === "granted".
// admin=true registers this device for Admin-Panel alerts (uses the admin JWT).
export async function registerAndSyncToken({ admin = false } = {}) {
  const client = admin ? adminApi : api;
  const base = admin ? "/admin/push/token" : "/push/token";
  const key = admin ? ADMIN_TOKEN_KEY : TOKEN_KEY;
  const cfg = await loadPushConfig();
  if (!cfg?.configured) throw new Error("Firebase ещё не настроен");
  const swUrl = `/firebase-messaging-sw.js?firebaseConfig=${b64(toFirebaseOptions(cfg))}`;
  const reg = await navigator.serviceWorker.register(swUrl, { scope: "/" });
  await navigator.serviceWorker.ready;
  const messaging = await getBrowserMessaging();
  if (!messaging) throw new Error("FCM не поддерживается");
  const token = await getToken(messaging, { vapidKey: cfg.vapidKey, serviceWorkerRegistration: reg });
  if (!token) throw new Error("FCM не вернул токен");
  const prev = localStorage.getItem(key);
  await client.post(base, { token, platform: "web" });
  if (prev && prev !== token) { try { await client.delete(base, { data: { token: prev } }); } catch { /* noop */ } }
  localStorage.setItem(key, token);
  return token;
}

export function usePushNotifications(currentUser) {
  const [permission, setPermission] = useState(typeof Notification !== "undefined" ? Notification.permission : "default");
  const [serverConfigured, setServerConfigured] = useState(false);
  const [subscribing, setSubscribing] = useState(false);
  const [subscribedToken, setSubscribedToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const supported = pushSupported();

  useEffect(() => {
    if (!currentUser) return;
    let cancelled = false;
    loadPushConfig(true).then((c) => { if (!cancelled) setServerConfigured(Boolean(c?.configured)); });
    return () => { cancelled = true; };
  }, [currentUser]);

  const subscribe = useCallback(async () => {
    if (!supported) throw new Error("Браузер не поддерживает Web Push");
    if (isIOSNonStandalone()) throw new Error("На iOS сначала добавьте приложение на главный экран");
    setSubscribing(true);
    try {
      const perm = await Notification.requestPermission();
      setPermission(perm);
      if (perm !== "granted") throw new Error("Разрешение на уведомления отклонено");
      const token = await registerAndSyncToken();
      setSubscribedToken(token);
      return token;
    } finally {
      setSubscribing(false);
    }
  }, [supported]);

  const unsubscribe = useCallback(async () => {
    setSubscribing(true);
    try {
      const token = subscribedToken || localStorage.getItem(TOKEN_KEY);
      const messaging = await getBrowserMessaging();
      if (messaging) { try { await deleteToken(messaging); } catch { /* noop */ } }
      if (token) { try { await api.delete("/push/token", { data: { token } }); } catch { /* noop */ } }
      localStorage.removeItem(TOKEN_KEY);
      setSubscribedToken(null);
    } finally {
      setSubscribing(false);
    }
  }, [subscribedToken]);

  const sendTest = useCallback(async () => (await api.post("/push/test")).data, []);

  return { supported, serverConfigured, permission, subscribing, subscribedToken, subscribe, unsubscribe, sendTest };
}
