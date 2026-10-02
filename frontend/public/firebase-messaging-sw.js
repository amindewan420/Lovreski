/* Firebase Cloud Messaging — Service Worker
 * Config values are passed in via the ?firebaseConfig=<base64-json> query string
 * during navigator.serviceWorker.register(). This avoids hard-coding secrets
 * and works with CRA (which doesn't process env vars inside /public/).
 */
/* eslint-disable no-restricted-globals */
/* global firebase, importScripts, self */
importScripts("https://www.gstatic.com/firebasejs/12.18.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/12.18.0/firebase-messaging-compat.js");

let messagingInstance = null;
try {
  const url = new URL(self.location.href);
  const raw = url.searchParams.get("firebaseConfig");
  if (raw) {
    const cfg = JSON.parse(atob(raw));
    if (cfg && cfg.apiKey && cfg.projectId) {
      firebase.initializeApp(cfg);
      messagingInstance = firebase.messaging();
    }
  }
} catch (e) {
  console.warn("[fcm-sw] init failed:", e);
}

if (messagingInstance) {
  messagingInstance.onBackgroundMessage((payload) => {
    // If FCM already carries a notification payload, the browser displays it
    // automatically — avoid duplicates by only handling data-only messages.
    if (payload && payload.notification) return;
    const d = payload && payload.data ? payload.data : {};
    self.registration.showNotification(d.title || "Lovreski", {
      body: d.body || "Новое уведомление",
      icon: "/logo192.png",
      badge: "/logo192.png",
      tag: d.tag || d.type || "lovreski",
      data: { url: d.url || "/" },
    });
  });
}

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((all) => {
      // Focus an existing tab if one is open
      for (const c of all) {
        if ("focus" in c) { c.navigate(url); return c.focus(); }
      }
      if (self.clients.openWindow) return self.clients.openWindow(url);
    })
  );
});
