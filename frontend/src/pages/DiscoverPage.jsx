import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { MobileShell } from "@/components/lovreski/Shell";
import { MatchCelebration } from "@/components/lovreski/MatchCelebration";
import { motion, AnimatePresence, useMotionValue, useTransform } from "framer-motion";
import { Heart, X, Star, MessageCircle, MapPin, ShieldCheck, Crown } from "lucide-react";
import { toast } from "sonner";
import { Link } from "react-router-dom";

const SwipeCard = ({ user, onSwipe, top }) => {
  const x = useMotionValue(0);
  const rotate = useTransform(x, [-200, 200], [-25, 25]);
  const likeOp = useTransform(x, [0, 150], [0, 1]);
  const nopeOp = useTransform(x, [-150, 0], [1, 0]);
  return (
    <motion.div
      data-testid={`swipe-card-${user.user_id}`}
      className="absolute inset-0"
      style={{ x, rotate, zIndex: top ? 20 : 10 }}
      drag={top ? "x" : false}
      dragConstraints={{ left: 0, right: 0 }}
      onDragEnd={(_, info) => {
        if (info.offset.x > 120) onSwipe("like");
        else if (info.offset.x < -120) onSwipe("pass");
      }}
      whileTap={{ cursor: "grabbing" }}
    >
      <div className="relative w-full h-full rounded-3xl overflow-hidden bg-card shadow-2xl border border-border/60">
        <img src={user.photos?.[0] || `https://api.dicebear.com/9.x/avataaars/svg?seed=${user.user_id}`} alt={user.name} className="w-full h-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/25 to-transparent" />
        <motion.div style={{ opacity: likeOp }} className="absolute top-8 left-6 rotate-[-15deg] border-4 border-emerald-400 text-emerald-400 px-4 py-1 rounded-lg font-black text-2xl">СИМПАТИЯ</motion.div>
        <motion.div style={{ opacity: nopeOp }} className="absolute top-8 right-6 rotate-[15deg] border-4 border-rose-500 text-rose-500 px-4 py-1 rounded-lg font-black text-2xl">ПРОПУСК</motion.div>
        <div className="absolute inset-x-0 bottom-0 p-5 text-white">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            {user.verified && <ShieldCheck className="w-5 h-5 text-sky-400" />}
            {user.is_premium && <span className="inline-flex items-center gap-1 bg-accent text-accent-foreground text-[10px] font-bold px-2 py-0.5 rounded-full"><Crown className="w-3 h-3" />PREMIUM</span>}
            {user.online && <span className="inline-flex items-center gap-1 bg-emerald-500 text-white text-[10px] font-semibold px-2 py-0.5 rounded-full">онлайн</span>}
          </div>
          <h2 className="font-display font-black text-3xl leading-tight">{user.name}, {user.age}</h2>
          {user.city && <p className="flex items-center gap-1 opacity-90 mt-1"><MapPin className="w-4 h-4" />{user.city}{user.distance_km != null ? ` · ${user.distance_km} км` : ""}</p>}
          {user.about && <p className="mt-2 opacity-95 text-sm line-clamp-3">{user.about}</p>}
          {user.interests?.length > 0 && (
            <div className="flex gap-1.5 mt-3 flex-wrap">
              {user.interests.slice(0, 4).map((i) => (
                <span key={i} className="text-[10px] font-semibold px-2 py-1 rounded-full bg-white/15 backdrop-blur-sm border border-white/20">{i}</span>
              ))}
            </div>
          )}
          <Link to={`/profile/${user.user_id}`} className="inline-block mt-3 text-xs underline opacity-80">Открыть профиль →</Link>
        </div>
      </div>
    </motion.div>
  );
};

export default function DiscoverPage() {
  const [feed, setFeed] = useState([]);
  const [loading, setLoading] = useState(true);
  const [matchUser, setMatchUser] = useState(null);

  const load = async () => {
    try {
      const { data } = await api.get("/discover/feed?limit=25");
      if (data.length === 0) { try { await api.post("/demo/seed"); } catch {}; const r = await api.get("/discover/feed?limit=25"); setFeed(r.data); }
      else setFeed(data);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const act = async (kind) => {
    const u = feed[feed.length - 1];
    if (!u) return;
    setFeed((f) => f.slice(0, -1));
    try {
      if (kind === "like") {
        const { data } = await api.post(`/like/${u.user_id}`);
        if (data.match) setMatchUser(data.target || u);
      } else {
        await api.post(`/pass/${u.user_id}`);
      }
    } catch { toast.error("Ошибка"); }
    if (feed.length <= 3) load();
  };

  return (
    <MobileShell>
      <header className="px-4 pt-4 pb-2">
        <h1 className="font-display font-black text-2xl tracking-tight">Поиск</h1>
        <p className="text-xs text-muted-foreground">Смахните вправо, если нравится</p>
      </header>
      <div className="relative mx-4 mt-2" style={{ height: "70vh" }}>
        {loading ? (
          <div className="w-full h-full rounded-3xl bg-muted animate-pulse" />
        ) : feed.length === 0 ? (
          <div className="w-full h-full flex flex-col items-center justify-center rounded-3xl border-2 border-dashed border-border">
            <p className="text-muted-foreground">Больше нет анкет</p>
            <button onClick={load} className="mt-3 btn-pill bg-primary text-primary-foreground">Обновить</button>
          </div>
        ) : (
          <AnimatePresence>
            {feed.slice(-3).map((u, idx, arr) => (
              <SwipeCard key={u.user_id} user={u} top={idx === arr.length - 1} onSwipe={act} />
            ))}
          </AnimatePresence>
        )}
      </div>
      <div className="flex items-center justify-center gap-4 mt-4 px-4">
        <button data-testid="btn-swipe-pass" onClick={() => act("pass")} className="w-14 h-14 rounded-full bg-card border-2 border-border shadow-lg flex items-center justify-center text-rose-500 hover:scale-110 transition-transform duration-200">
          <X className="w-7 h-7" />
        </button>
        <button data-testid="btn-swipe-star" className="w-12 h-12 rounded-full bg-card border-2 border-border shadow flex items-center justify-center text-sky-500 hover:scale-110 transition-transform duration-200">
          <Star className="w-5 h-5" />
        </button>
        <button data-testid="btn-swipe-like" onClick={() => act("like")} className="w-14 h-14 rounded-full bg-primary shadow-lg shadow-primary/30 flex items-center justify-center text-primary-foreground hover:scale-110 transition-transform duration-200">
          <Heart className="w-7 h-7 fill-current" />
        </button>
      </div>
      <AnimatePresence>
        {matchUser && <MatchCelebration matchUser={matchUser} onClose={() => setMatchUser(null)} />}
      </AnimatePresence>
    </MobileShell>
  );
}
