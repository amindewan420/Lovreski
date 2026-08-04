import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { createChatSocket } from "@/lib/ws";
import { MobileShell } from "@/components/lovreski/Shell";
import { useNavigate } from "react-router-dom";
import { MessageCircle } from "lucide-react";

export default function ChatsListPage() {
  const [chats, setChats] = useState([]);
  const [loading, setLoading] = useState(true);
  const nav = useNavigate();
  const sockRef = useRef(null);

  const load = async () => {
    try {
      const { data } = await api.get("/chats");
      setChats(data);
    } finally { setLoading(false); }
  };

  useEffect(() => {
    load();
    // Real-time refresh on any incoming/outgoing chat message
    sockRef.current = createChatSocket({
      onMessage: () => { load(); },
    });
    return () => sockRef.current?.close();
  }, []);

  return (
    <MobileShell>
      <header className="sticky top-0 z-40 bg-background/85 backdrop-blur-xl px-4 pt-4 pb-3 border-b border-border/50">
        <h1 className="font-display font-black text-2xl tracking-tight">Чаты</h1>
      </header>
      <div className="divide-y divide-border">
        {loading ? (
          [...Array(4)].map((_, i) => <div key={i} className="h-16 bg-muted/50 animate-pulse" />)
        ) : chats.length === 0 ? (
          <div className="text-center py-20 px-6">
            <MessageCircle className="w-12 h-12 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground">Начните общение из вкладки Поиск</p>
          </div>
        ) : (
          chats.map((c) => {
            const last = c.last_message || {};
            const preview =
              last.kind === "gift" ? "🎁 Подарок" :
              last.kind === "image" ? "📷 Фото" :
              last.kind === "voice" ? "🎤 Голосовое" :
              last.kind === "video" ? "🎥 Видео" :
              last.text || "...";
            return (
              <button
                key={c.chat_id}
                data-testid={`chat-item-${c.user.user_id}`}
                onClick={() => nav(`/chats/${c.user.user_id}`)}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-muted/50 transition-colors duration-200"
              >
                <div className="relative">
                  <img src={c.user.photos?.[0]} alt="" className="w-14 h-14 rounded-full object-cover" />
                  {c.user.online && <span className="absolute bottom-0 right-0 w-3.5 h-3.5 rounded-full bg-emerald-500 border-2 border-background" />}
                </div>
                <div className="flex-1 text-left min-w-0">
                  <div className="flex justify-between items-baseline gap-2">
                    <p className="font-semibold truncate">{c.user.name}, {c.user.age}</p>
                    <p className="text-[10px] text-muted-foreground">{new Date(last.created_at).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })}</p>
                  </div>
                  <p className="text-sm text-muted-foreground truncate">{preview}</p>
                </div>
                {c.unread > 0 && <span className="bg-primary text-primary-foreground text-xs font-bold px-2 py-0.5 rounded-full">{c.unread}</span>}
              </button>
            );
          })
        )}
      </div>
    </MobileShell>
  );
}
