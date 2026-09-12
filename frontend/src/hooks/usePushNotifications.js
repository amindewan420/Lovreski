// Push notifications hook — subscribes/unsubscribes to FCM Web Push
// and shows a toast when a foreground message arrives.
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { FCM_CONFIGURED, VAPID_KEY, getBrowserMessaging } from "@/lib/firebase";
import { getToken, onMessage, deleteToken } from "firebase/messaging";

const b64 = (obj) =>
  btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(obj))));

function buildSwUrl() {
  const cfg = {
    apiKey: process.env.REACT_APP_FIREBASE_API_KEY,
    authDomain: process.env.REACT_APP_FIREBASE_AUTH_DOMAIN,
    projectId: process.env.REACT_APP_FIREBASE_PROJECT_ID,
    storageBucket: process.env.REACT_APP_FIREBASE_STORAGE_BUCKET,
    messagingSenderId: process.env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID,
    appId: process.env.REACT_APP_FIREBASE_APP_ID,
  };
  return `/firebase-messaging-sw.js?firebaseConfig=${b64(cfg)}`;
}

export function usePushNotifications(currentUser) {
  const [permission, setPermission] = useState(
    typeof Notification !== "undefined" ? Notification.permission : "default"
  );
  const [supported, setSupported] = useState(false);
  const [serverConfigured, setServerConfigured] = useState(FCM_CONFIGURED);
  const [subscribing, setSubscribing] = useState(false);
  const [subscribedToken, setSubscribedToken] = useState(null);

  // Detect support once
  useEffect(() => {
    if (!("serviceWorker" in navigator) || !("Notification" in window)) {
      setSupported(false); return;
    }
    setSupported(true);
  }, []);

  // Check server-side config on mount
  useEffect(() => {
    if (!currentUser) return;
    let cancelled = false;
    api.get("/push/status")
      .then((r) => { if (!cancelled) setServerConfigured(Boolean(r.data?.configured) && FCM_CONFIGURED); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [currentUser]);

  // Foreground message → toast
  useEffect(() => {
    if (!FCM_CONFIGURED) return;
    let unsub;
    getBrowserMessaging().then((m) => {
      if (!m) return;
      unsub = onMessage(m, (payload) => {
        const title = payload.notification?.title || payload.data?.title || "Lovreski";
        const body  = payload.notification?.body  || payload.data?.body  || "";
        const url   = payload.data?.url || payload.fcmOptions?.link || "/";
        toast(title, {
          description: body,
          action: url && url !== "/" ? { label: "Открыть", onClick: () => (window.location.href = url) } : undefined,
        });
      });
    });
    return () => { if (unsub) unsub(); };
  }, []);

  const subscribe = useCallback(async () => {
    if (!supported) throw new Error("Браузер не поддерживает Web Push");
    if (!FCM_CONFIGURED || !serverConfigured) throw new Error("Firebase ещё не настроен");
    setSubscribing(true);
    try {
      // iOS Safari requires PWA installed to Home Screen
      const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
      const standalone = window.matchMedia("(display-mode: standalone)").matches
        || window.navigator.standalone === true;
      if (isIOS && !standalone) {
        throw new Error("На iOS сначала добавьте приложение на главный экран");
      }
      const perm = await Notification.requestPermission();
      setPermission(perm);
      if (perm !== "granted") throw new Error("Разрешение на уведомления отклонено");

      const reg = await navigator.serviceWorker.register(buildSwUrl(), { scope: "/" });
      const messaging = await getBrowserMessaging();
      if (!messaging) throw new Error("FCM не поддерживается");
      const token = await getToken(messaging, { vapidKey: VAPID_KEY, serviceWorkerRegistration: reg });
      if (!token) throw new Error("FCM не вернул токен");

      await api.post("/push/token", { token, platform: "web" });
      setSubscribedToken(token);
      try { localStorage.setItem("lovreski_fcm_token", token); } catch { /* noop */ }
      return token;
    } finally {
      setSubscribing(false);
    }
  }, [supported, serverConfigured]);

  const unsubscribe = useCallback(async () => {
    setSubscribing(true);
    try {
      const messaging = await getBrowserMessaging();
      let token = subscribedToken;
      try { token = token || localStorage.getItem("lovreski_fcm_token"); } catch { /* noop */ }
      if (messaging) { try { await deleteToken(messaging); } catch { /* noop */ } }
      if (token) {
        try { await api.delete("/push/token", { data: { token } }); } catch { /* noop */ }
        try { localStorage.removeItem("lovreski_fcm_token"); } catch { /* noop */ }
      }
      setSubscribedToken(null);
    } finally {
      setSubscribing(false);
    }
  }, [subscribedToken]);

  const sendTest = useCallback(async () => {
    const r = await api.post("/push/test");
    return r.data;
  }, []);

  return {
    supported,
    serverConfigured,
    permission,
    subscribing,
    subscribedToken: subscribedToken || (typeof localStorage !== "undefined" ? localStorage.getItem("lovreski_fcm_token") : null),
    subscribe,
    unsubscribe,
    sendTest,
  };
}
