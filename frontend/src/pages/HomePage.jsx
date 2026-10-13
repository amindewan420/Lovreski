import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { MobileShell } from "@/components/lovreski/Shell";
import { ProfileCard } from "@/components/lovreski/ProfileCard";
import { MatchCelebration } from "@/components/lovreski/MatchCelebration";
import { AnimatePresence } from "framer-motion";
import { Search, Bell, SlidersHorizontal, Download, X } from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

const INSTALL_DISMISS_KEY = "lovreski_pwa_dismissed";

// Show install banner ONLY on mobile browsers that haven't installed the PWA,
// and haven't been dismissed yet.
const shouldShowInstallBanner = () => {
  if (typeof window === "undefined") return false;
  if (localStorage.getItem(INSTALL_DISMISS_KEY) === "1") return false;
  // Already installed as PWA?
  const standalone = window.matchMedia?.("(display-mode: standalone)").matches
    || window.navigator.standalone === true;
  if (standalone) return false;
  // Mobile UA heuristic (iOS/Android/Mobile keywords)
  const ua = navigator.userAgent || "";
  return /Android|iPhone|iPad|iPod|Mobile|Opera Mini|IEMobile/i.test(ua);
};

export default function HomePage() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [feed, setFeed] = useState([]);
  const [loading, setLoading] = useState(true);
  const [matchUser, setMatchUser] = useState(null);
  const [showInstall, setShowInstall] = useState(() => shouldShowInstallBanner());
  const [deferred, setDeferred] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        // Refresh location on every app open (per profile spec section 5)
        if (navigator.geolocation) {
          navigator.geolocation.getCurrentPosition(async (pos) => {
            try {
              await api.put("/profile/location", { lat: pos.coords.latitude, lng: pos.coords.longitude });
            } catch {}
            load();
          }, () => load(), { timeout: 5000 });
        } else load();
      } catch { load(); }
    })();
    const handler = (e) => { e.preventDefault(); setDeferred(e); if (shouldShowInstallBanner()) setShowInstall(true); };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
    // eslint-disable-next-line
  }, []);

  const load = async () => {
    try {
      const { data } = await api.get("/home/feed?limit=6");
      if (data.length === 0) {
        // Attempt seed once
        try { await api.post("/demo/seed"); } catch {}
        const r = await api.get("/home/feed?limit=6");
        setFeed(r.data);
      } else setFeed(data);
    } catch (e) {
      toast.error("Не удалось загрузить ленту");
    } finally {
      setLoading(false);
    }
  };

  const doLike = async (u) => {
    try {
      const { data } = await api.post(`/like/${u.user_id}`);
      setFeed((f) => f.filter((x) => x.user_id !== u.user_id));
      if (data.match) setMatchUser(data.target || u);
      else toast.success(`Симпатия отправлена ${u.name}`);
    } catch { toast.error("Ошибка"); }
  };
  const doPass = async (u) => {
    try {
      await api.post(`/pass/${u.user_id}`);
      setFeed((f) => f.filter((x) => x.user_id !== u.user_id));
    } catch { toast.error("Ошибка"); }
  };

  const install = async () => {
    if (deferred) {
      deferred.prompt();
      const { outcome } = await deferred.userChoice;
      if (outcome === "accepted") { setShowInstall(false); localStorage.setItem(INSTALL_DISMISS_KEY, "1"); }
      return;
    }
    // iOS Safari has no beforeinstallprompt — surface the shelf hint instead.
    toast.info("Нажмите «Поделиться» → «На экран Домой» чтобы установить");
  };
  const dismissInstall = () => { setShowInstall(false); localStorage.setItem(INSTALL_DISMISS_KEY, "1"); };

  return (
    <MobileShell>
      <header className="sticky top-0 z-40 bg-background/85 backdrop-blur-xl px-4 pt-4 pb-3 border-b border-border/50">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h1 className="font-display font-black text-2xl tracking-tight">Главная</h1>
            <p className="text-xs text-muted-foreground">Привет, {user?.name} 👋</p>
          </div>
          <div className="flex items-center gap-2">
            <button data-testid="btn-filters" onClick={() => nav("/settings/discovery")} className="p-2 rounded-full bg-muted hover:bg-muted/70 transition-colors duration-200">
              <SlidersHorizontal className="w-5 h-5" />
            </button>
            <button data-testid="btn-search" onClick={() => nav("/discover")} className="p-2 rounded-full bg-muted hover:bg-muted/70 transition-colors duration-200">
              <Search className="w-5 h-5" />
            </button>
          </div>
        </div>
        {showInstall && (
          <div
            data-testid="pwa-install-banner"
            className="flex items-center gap-3 px-3 py-2.5 rounded-2xl bg-gradient-to-r from-primary to-fuchsia-500 text-primary-foreground shadow-lg"
          >
            <div className="w-9 h-9 rounded-xl bg-white/20 flex items-center justify-center shrink-0">
              <Download className="w-5 h-5" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold leading-tight">Install Lovreski App</p>
              <p className="text-[11px] opacity-90 leading-tight">for a better experience</p>
            </div>
            <button
              data-testid="pwa-install-btn"
              onClick={install}
              className="px-3 py-1.5 rounded-full bg-white text-primary text-xs font-bold hover:bg-white/90"
            >
              Install
            </button>
            <button
              data-testid="pwa-install-dismiss"
              onClick={dismissInstall}
              aria-label="Закрыть"
              className="p-1.5 rounded-full hover:bg-white/15"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}
      </header>

      <div className="p-4">
        {loading ? (
          <div className="grid grid-cols-2 gap-3">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="aspect-[3/4] bg-muted animate-pulse rounded-2xl" />
            ))}
          </div>
        ) : feed.length === 0 ? (
          <div className="text-center py-16">
            <p className="text-muted-foreground">Пока никого нет поблизости 😔</p>
            <button onClick={load} className="mt-4 btn-pill bg-primary text-primary-foreground">Обновить</button>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3" data-testid="home-grid">
            {feed.map((u) => (
              <ProfileCard key={u.user_id} user={u} onLike={doLike} onPass={doPass} />
            ))}
          </div>
        )}
      </div>
      <AnimatePresence>
        {matchUser && <MatchCelebration matchUser={matchUser} onClose={() => setMatchUser(null)} />}
      </AnimatePresence>
    </MobileShell>
  );
}
