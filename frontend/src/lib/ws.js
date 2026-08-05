// Chat / presence WebSocket client for Lovreski
import { getToken } from "./api";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

// Convert https://x.emergent... → wss://x.emergent.../api/ws?token=...
function wsUrl() {
  const token = getToken();
  const base = BACKEND_URL.replace(/^http/, "ws");
  return `${base}/api/ws?token=${encodeURIComponent(token || "")}`;
}

export function createChatSocket({ onMessage, onTyping, onRead, onDeleted, onOpen, onClose }) {
  let ws = null;
  let closedByUser = false;
  let retryDelay = 1000;
  let pingTimer = null;

  const connect = () => {
    try {
      ws = new WebSocket(wsUrl());
    } catch {
      scheduleReconnect();
      return;
    }
    ws.onopen = () => {
      retryDelay = 1000;
      onOpen?.();
      pingTimer = setInterval(() => {
        try { ws?.readyState === 1 && ws.send(JSON.stringify({ type: "ping" })); } catch { /* noop */ }
      }, 25000);
    };
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === "message") onMessage?.(data.data);
        else if (data.type === "typing") onTyping?.(data.from);
        else if (data.type === "read") onRead?.(data.from);
        else if (data.type === "message_deleted") onDeleted?.(data.data);
      } catch { /* noop */ }
    };
    ws.onclose = () => {
      clearInterval(pingTimer); pingTimer = null;
      onClose?.();
      if (!closedByUser) scheduleReconnect();
    };
    ws.onerror = () => { try { ws?.close(); } catch { /* noop */ } };
  };

  const scheduleReconnect = () => {
    setTimeout(() => { if (!closedByUser) connect(); }, retryDelay);
    retryDelay = Math.min(retryDelay * 2, 15000);
  };

  const send = (obj) => { try { ws?.readyState === 1 && ws.send(JSON.stringify(obj)); } catch { /* noop */ } };
  const close = () => { closedByUser = true; try { ws?.close(); } catch { /* noop */ } clearInterval(pingTimer); };

  connect();
  return { send, close };
}
