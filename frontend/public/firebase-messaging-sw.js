/* Firebase Cloud Messaging — Service Worker
 * Web config arrives via ?firebaseConfig=<base64-json> (set by the app from the
 * Admin-Panel Firebase settings). Backend sends data-only messages, so this SW
 * renders every background notification and handles tap-to-navigate.
 */
self.importScripts("https://www.gstatic.com/firebasejs/12.18.0/firebase-app-compat.js");
self.importScripts("https://www.gstatic.com/firebasejs/12.18.0/firebase-messaging-compat.js");

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

let messagingInstance = null;
try {
  const raw = new URL(self.location.href).searchParams.get("firebaseConfig");
  if (raw) {
    const cfg = JSON.parse(atob(raw));
    if (cfg && cfg.apiKey && cfg.projectId) {
      self.firebase.initializeApp(cfg);
      messagingInstance = self.firebase.messaging();
    }
  }
} catch (e) {
  console.warn("[fcm-sw] init failed:", e);
}

if (messagingInstance) {
  messagingInstance.onBackgroundMessage((payload) => {
    if (payload && payload.notification) return; // browser already shows these
    const d = (payload && payload.data) || {};
    return self.registration.showNotification(d.title || "Lovreski", {
      body: d.body || "Новое уведомление",
      icon: "/logo192.png",
      badge: "/logo192.png",
      tag: d.tag || d.type || "lovreski",
      renotify: true,
      data: { url: d.url || "/" },
    });
  });
}

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const path = (event.notification.data && event.notification.data.url) || "/";
  const target = new URL(path, self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((all) => {
      const client = all.find((c) => c.url.startsWith(self.location.origin));
      if (client) {
        client.postMessage({ type: "push-navigate", url: path });
        return client.focus();
      }
      return self.clients.openWindow ? self.clients.openWindow(target) : undefined;
    })
  );
});
