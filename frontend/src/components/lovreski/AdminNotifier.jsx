import { useEffect, useRef } from "react";
import { adminApi as api, getAdminToken } from "@/lib/adminApi";
import { toast } from "sonner";
import { useNavigate, useLocation } from "react-router-dom";

/**
 * AdminNotifier — mounts globally. When user.is_admin is true, polls the
 * pending-receipts count every 10s. If it INCREASES since the last poll, fires:
 *   - Sonner toast with a click-to-open action
 *   - Native browser Notification (if permission granted)
 *   - Optional bell sound (WebAudio beep) — non-intrusive
 *
 * Ignores the very first poll to avoid a startup false-positive.
 */
export default function AdminNotifier() {
  const loc = useLocation();
  const isAdmin = loc.pathname.startsWith("/admin") && loc.pathname !== "/admin/login" && !!getAdminToken();
  const nav = useNavigate();
  const lastCount = useRef(null);

  // Ask for Notification permission once per admin session
  useEffect(() => {
    if (!isAdmin) return;
    if ("Notification" in window && Notification.permission === "default") {
      // Non-blocking: ignore rejection silently
      Notification.requestPermission().catch(() => {});
    }
  }, [isAdmin]);

  useEffect(() => {
    if (!isAdmin) { lastCount.current = null; return; }
    let cancelled = false;

    const poll = async () => {
      // Skip polling when the tab is hidden to reduce load
      if (typeof document !== "undefined" && document.hidden) return;
      try {
        const { data } = await api.get("/admin/support/pending-count");
        const cur = data?.count ?? 0;
        if (cancelled) return;
        if (lastCount.current !== null && cur > lastCount.current) {
          const delta = cur - lastCount.current;
          const msg = `🔔 ${delta} new receipt${delta > 1 ? "s" : ""} awaiting review · total pending: ${cur}`;
          toast.info(msg, {
            duration: 8000,
            action: {
              label: "Open",
              onClick: () => nav("/admin/dashboard"),
            },
          });
          // Native browser notification (works even when tab is backgrounded)
          try {
            if ("Notification" in window && Notification.permission === "granted") {
              const n = new Notification("Lovreski Admin", {
                body: `${delta} new receipt${delta > 1 ? "s" : ""} to verify (${cur} total)`,
                icon: "/favicon.ico",
                tag: "lovreski-admin-receipt",
              });
              n.onclick = () => { window.focus(); nav("/admin/dashboard"); n.close(); };
            }
          } catch { /* not-supported */ }
          // Soft chime — 440 Hz for 120 ms
          try {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (AC) {
              const ctx = new AC();
              const osc = ctx.createOscillator();
              const gain = ctx.createGain();
              osc.type = "sine";
              osc.frequency.value = 880;
              gain.gain.value = 0.05;
              osc.connect(gain).connect(ctx.destination);
              osc.start();
              setTimeout(() => { osc.stop(); ctx.close(); }, 120);
            }
          } catch { /* audio blocked, silent */ }
        }
        lastCount.current = cur;
      } catch { /* not admin or offline — ignore */ }
    };

    // Immediate first poll to establish baseline
    poll();
    const t = setInterval(poll, 10000);
    return () => { cancelled = true; clearInterval(t); };
  }, [isAdmin, nav]);

  return null;
}
