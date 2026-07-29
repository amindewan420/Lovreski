import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { MobileShell } from "@/components/lovreski/Shell";
import { ProfileCard } from "@/components/lovreski/ProfileCard";
import { useNavigate } from "react-router-dom";

const tabs = [
  { key: "received", label: "Получено" },
  { key: "sent", label: "Отправлено" },
  { key: "matches", label: "Совпадения" },
];

export default function LikesPage() {
  const [tab, setTab] = useState("received");
  const [data, setData] = useState({ received: [], sent: [], matches: [] });
  const [loading, setLoading] = useState(true);
  const nav = useNavigate();

  useEffect(() => {
    (async () => {
      const [r, s, m] = await Promise.all([
        api.get("/likes/received"),
        api.get("/likes/sent"),
        api.get("/likes/matches"),
      ]);
      setData({ received: r.data, sent: s.data, matches: m.data });
      setLoading(false);
    })();
  }, []);

  const list = data[tab] || [];

  return (
    <MobileShell>
      <header className="sticky top-0 z-40 bg-background/85 backdrop-blur-xl px-4 pt-4 pb-2 border-b border-border/50">
        <h1 className="font-display font-black text-2xl tracking-tight mb-3">Симпатии</h1>
        <div className="flex bg-muted rounded-full p-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              data-testid={`likes-tab-${t.key}`}
              onClick={() => setTab(t.key)}
              className={`flex-1 py-2 rounded-full text-xs font-semibold transition-colors duration-200 ${tab === t.key ? "bg-card text-foreground shadow" : "text-muted-foreground"}`}
            >
              {t.label}
              {data[t.key]?.length > 0 && <span className="ml-1 opacity-70">({data[t.key].length})</span>}
            </button>
          ))}
        </div>
      </header>
      <div className="p-4">
        {loading ? (
          <div className="grid grid-cols-2 gap-3">{[...Array(4)].map((_, i) => <div key={i} className="aspect-[3/4] bg-muted animate-pulse rounded-2xl" />)}</div>
        ) : list.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground">
            {tab === "received" && "Пока никто не поставил вам симпатию"}
            {tab === "sent" && "Вы никого не лайкнули"}
            {tab === "matches" && "Пока нет взаимных симпатий"}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {list.map((u) => (
              <div key={u.user_id} onClick={() => tab === "matches" ? nav(`/chats/${u.user_id}`) : nav(`/profile/${u.user_id}`)}>
                <ProfileCard user={u} compact />
              </div>
            ))}
          </div>
        )}
      </div>
    </MobileShell>
  );
}
