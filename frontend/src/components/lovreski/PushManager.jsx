// Global push glue: silent token re-sync on login, foreground toasts,
// SW tap-to-navigate, and a one-time "enable notifications" prompt.
import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { onMessage } from "firebase/messaging";
import { BellRing, X } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/lib/i18n";
import { loadPushConfig, getBrowserMessaging } from "@/lib/firebase";
import { pushSupported, isIOSNonStandalone, registerAndSyncToken } from "@/hooks/usePushNotifications";

const PROMPT_KEY = "lovreski_push_prompt_dismissed";

export default function PushManager() {
  const { user } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const { t } = useI18n();
  const [showPrompt, setShowPrompt] = useState(false);

  // Tap on a background notification → in-app navigation
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    const onMsg = (e) => { if (e.data?.type === "push-navigate" && e.data.url) nav(e.data.url); };
    navigator.serviceWorker.addEventListener("message", onMsg);
    return () => navigator.serviceWorker.removeEventListener("message", onMsg);
  }, [nav]);

  // On login: sync token silently if already granted, else maybe show prompt
  useEffect(() => {
    if (!user || !pushSupported()) return;
    let unsub; let cancelled = false;
    loadPushConfig(true).then(async (cfg) => {
      if (cancelled || !cfg?.configured) return;
      if (Notification.permission === "granted") {
        try { await registerAndSyncToken(); } catch (e) { console.warn("[fcm] sync failed", e); }
        const m = await getBrowserMessaging();
        if (m && !cancelled) {
          unsub = onMessage(m, (p) => {
            const d = p.data || {};
            const url = d.url || "/";
            toast(d.title || p.notification?.title || "Lovreski", {
              description: d.body || p.notification?.body || "",
              action: url !== "/" ? { label: t("push.open"), onClick: () => nav(url) } : undefined,
            });
          });
        }
      } else if (Notification.permission === "default" && !localStorage.getItem(PROMPT_KEY) && !isIOSNonStandalone()) {
        setShowPrompt(true);
      }
    });
    return () => { cancelled = true; if (unsub) unsub(); };
    // eslint-disable-next-line
  }, [user?.user_id]);

  const enable = async () => {
    setShowPrompt(false);
    localStorage.setItem(PROMPT_KEY, "1");
    try {
      const perm = await Notification.requestPermission();
      if (perm !== "granted") return toast.error(t("push.denied"));
      await registerAndSyncToken();
      toast.success(t("settings.push_on_done"));
    } catch (e) { toast.error(e.message || t("common.error")); }
  };
  const later = () => { setShowPrompt(false); localStorage.setItem(PROMPT_KEY, "1"); };

  if (!showPrompt || loc.pathname.startsWith("/chats/") || loc.pathname === "/") return null;
  return (
    <div data-testid="push-prompt" className="fixed left-3 right-3 bottom-24 z-[60] sm:left-auto sm:right-6 sm:w-96 rounded-2xl bg-card border border-border shadow-2xl p-4 flex gap-3 animate-in slide-in-from-bottom-4">
      <div className="w-10 h-10 shrink-0 rounded-full bg-primary/15 text-primary flex items-center justify-center"><BellRing className="w-5 h-5" /></div>
      <div className="flex-1 min-w-0">
        <p className="font-display font-bold text-sm">{t("push.prompt_title")}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{t("push.prompt_body")}</p>
        <div className="flex gap-2 mt-3">
          <button data-testid="push-prompt-enable" onClick={enable} className="px-4 py-1.5 rounded-full bg-primary text-primary-foreground text-xs font-semibold">{t("push.enable")}</button>
          <button data-testid="push-prompt-later" onClick={later} className="px-4 py-1.5 rounded-full bg-muted text-xs font-semibold">{t("push.later")}</button>
        </div>
      </div>
      <button data-testid="push-prompt-close" onClick={later} className="self-start p-1 rounded-full hover:bg-muted"><X className="w-4 h-4" /></button>
    </div>
  );
}
