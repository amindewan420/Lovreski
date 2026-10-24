// Polls admin badge counts every 12s; marks refunds/complaints read when their tab is open.
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { onMessage } from "firebase/messaging";
import { adminApi } from "@/lib/adminApi";
import { getBrowserMessaging } from "@/lib/firebase";

const POLL_MS = 12000;
const MARK_READ = { refunds: "/admin/refund-requests/mark-read", reports: "/admin/complaints/mark-read" };

export function useAdminBadges(tab, { onNew } = {}) {
  const [badges, setBadges] = useState({ support: 0, refunds: 0, reports: 0 });
  const tabRef = useRef(tab);
  const onNewRef = useRef(onNew);
  tabRef.current = tab;
  onNewRef.current = onNew;

  const poll = useCallback(async () => {
    try {
      const [p, r, c] = await Promise.all([
        adminApi.get("/admin/support/pending-count"),
        adminApi.get("/admin/refund-requests/unread-count"),
        adminApi.get("/admin/complaints/unread-count"),
      ]);
      const next = { support: p.data?.count || 0, refunds: r.data?.count || 0, reports: c.data?.count || 0 };
      const open = tabRef.current;
      if (MARK_READ[open] && next[open] > 0) {
        await adminApi.post(MARK_READ[open]);
        onNewRef.current?.(open);
        next[open] = 0;
      }
      setBadges(next);
    } catch { /* keep last values */ }
  }, []);

  useEffect(() => {
    poll();
    const t = setInterval(() => { if (!document.hidden) poll(); }, POLL_MS);
    return () => clearInterval(t);
  }, [poll]);

  // Opening a tab marks its items read immediately
  useEffect(() => {
    if (!MARK_READ[tab]) return;
    setBadges((b) => ({ ...b, [tab]: 0 }));
    adminApi.post(MARK_READ[tab]).catch(() => {});
  }, [tab]);

  // Foreground admin pushes → toast + instant badge refresh
  useEffect(() => {
    if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
    let unsub;
    getBrowserMessaging().then((m) => {
      if (!m) return;
      unsub = onMessage(m, (p) => {
        const d = p.data || {};
        toast(d.title || "Lovreski Admin", { description: d.body || "" });
        poll();
      });
    });
    return () => { if (unsub) unsub(); };
  }, [poll]);

  return badges;
}
