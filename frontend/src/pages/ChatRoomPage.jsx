import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ArrowLeft, Send, Smile, Gift, Languages, Reply, X, Image as ImageIcon, Mic, Video } from "lucide-react";
import { toast } from "sonner";

const GIFTS = [
  { key: "heart", name: "Сердце", emoji: "❤️" },
  { key: "rose", name: "Роза", emoji: "🌹" },
  { key: "kiss", name: "Поцелуй", emoji: "💋" },
  { key: "crown", name: "Корона", emoji: "👑" },
  { key: "diamond", name: "Бриллиант", emoji: "💎" },
  { key: "bouquet", name: "Букет", emoji: "💐" },
  { key: "cake", name: "Торт", emoji: "🎂" },
  { key: "star", name: "Звезда", emoji: "⭐" },
];
const EMOJIS = ["😀","😍","😘","🥰","😂","🤣","😊","😉","😎","🥳","🤩","😜","🙈","🔥","💯","✨","🌈","💫","🎉","💕","💖","💘"];

export default function ChatRoomPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user, refresh } = useAuth();
  const [other, setOther] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const [reply, setReply] = useState(null);
  const [showGifts, setShowGifts] = useState(false);
  const [showEmoji, setShowEmoji] = useState(false);
  const scrollRef = useRef(null);

  const load = async () => {
    const [p, m] = await Promise.all([
      api.get(`/profile/${id}`),
      api.get(`/chats/${id}/messages`),
    ]);
    setOther(p.data); setMsgs(m.data);
    setTimeout(() => scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight), 50);
  };
  useEffect(() => { load(); const t = setInterval(load, 4000); return () => clearInterval(t); /* eslint-disable-next-line */ }, [id]);

  const send = async (payload) => {
    try {
      const { data } = await api.post(`/chats/${id}/send`, { ...payload, reply_to: reply?.message_id });
      setMsgs((prev) => [...prev, data]);
      setText(""); setReply(null); setShowGifts(false); setShowEmoji(false);
      refresh();
      setTimeout(() => scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight), 50);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Ошибка");
      if (e.response?.status === 402) nav("/premium");
    }
  };

  const doSend = () => { if (text.trim()) send({ text: text.trim(), kind: "text" }); };
  const sendGift = (g) => send({ text: g.emoji, kind: "gift", gift_key: g.key });
  const translate = async (m) => {
    try {
      const { data } = await api.post("/translate", { text: m.text, target: "ru" });
      setMsgs((p) => p.map((x) => x.message_id === m.message_id ? { ...x, translated: data.translated } : x));
    } catch { toast.error("Не удалось перевести"); }
  };

  return (
    <div className="min-h-screen bg-background flex justify-center">
      <div className="w-full max-w-md bg-background flex flex-col" style={{ minHeight: "100vh" }}>
        <header className="sticky top-0 z-30 flex items-center gap-3 px-3 py-3 bg-background/90 backdrop-blur-xl border-b border-border">
          <button data-testid="chat-back" onClick={() => nav(-1)} className="p-2 -ml-2 rounded-full hover:bg-muted"><ArrowLeft className="w-5 h-5" /></button>
          {other && (
            <>
              <img src={other.photos?.[0]} alt="" className="w-10 h-10 rounded-full object-cover" />
              <div className="flex-1 min-w-0">
                <p className="font-semibold truncate">{other.name}, {other.age}</p>
                <p className="text-[11px] text-emerald-500">{other.online ? "онлайн" : "недавно"}</p>
              </div>
            </>
          )}
        </header>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-4 space-y-2" style={{ minHeight: "60vh" }}>
          {msgs.map((m) => {
            const mine = m.from_user === user?.user_id;
            const replied = m.reply_to ? msgs.find((x) => x.message_id === m.reply_to) : null;
            return (
              <div key={m.message_id} data-testid={`msg-${m.message_id}`} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[75%] group ${mine ? "" : ""}`}>
                  {replied && (
                    <div className={`reply-line px-2 py-1 mb-1 text-xs opacity-80 rounded ${mine ? "bg-primary/10" : "bg-muted"}`}>
                      <p className="truncate">{replied.text || replied.kind}</p>
                    </div>
                  )}
                  <div className={`px-3 py-2 rounded-2xl ${mine ? "bg-primary text-primary-foreground rounded-tr-sm" : "bg-muted text-foreground rounded-tl-sm"}`}>
                    {m.kind === "gift" ? (
                      <div className="text-center">
                        <div className="text-5xl">{m.text}</div>
                        <div className="text-[10px] mt-1 opacity-80">🎁 Подарок</div>
                      </div>
                    ) : (
                      <p className="whitespace-pre-wrap break-words">{m.text}</p>
                    )}
                    {m.translated && <p className="mt-1 pt-1 border-t border-current/20 text-[11px] opacity-80 italic">{m.translated}</p>}
                  </div>
                  <div className={`flex gap-2 mt-0.5 text-[10px] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity ${mine ? "justify-end" : ""}`}>
                    <button onClick={() => setReply(m)}>Ответить</button>
                    {!mine && m.text && <button onClick={() => translate(m)}>Перевести</button>}
                  </div>
                </div>
              </div>
            );
          })}
          {msgs.length === 0 && (
            <div className="text-center text-muted-foreground text-sm py-16">Первые 2 сообщения бесплатны, дальше — 1 монета за сообщение</div>
          )}
        </div>

        {reply && (
          <div className="px-3 py-2 flex items-center gap-2 bg-muted border-t border-border">
            <Reply className="w-4 h-4 text-muted-foreground" />
            <div className="flex-1 text-xs truncate reply-line pl-2">Ответ: {reply.text}</div>
            <button onClick={() => setReply(null)}><X className="w-4 h-4" /></button>
          </div>
        )}

        {showEmoji && (
          <div className="grid grid-cols-8 gap-1 p-3 border-t border-border bg-card max-h-40 overflow-y-auto">
            {EMOJIS.map((e) => (
              <button key={e} data-testid={`emoji-${e}`} onClick={() => send({ text: e, kind: "emoji" })} className="text-2xl hover:scale-125 transition-transform duration-200">{e}</button>
            ))}
          </div>
        )}
        {showGifts && (
          <div className="grid grid-cols-4 gap-2 p-3 border-t border-border bg-card">
            {GIFTS.map((g) => (
              <button key={g.key} data-testid={`gift-${g.key}`} onClick={() => sendGift(g)} className="flex flex-col items-center p-2 rounded-xl bg-muted hover:bg-primary/10 transition-colors duration-200">
                <span className="text-3xl">{g.emoji}</span>
                <span className="text-[10px] mt-1">{g.name}</span>
                <span className="text-[10px] text-primary font-bold">10 💰</span>
              </button>
            ))}
          </div>
        )}

        <div className="sticky bottom-0 flex items-center gap-2 px-3 py-3 bg-background border-t border-border">
          <button data-testid="btn-emoji" onClick={() => { setShowEmoji((s) => !s); setShowGifts(false); }} className="p-2 rounded-full hover:bg-muted"><Smile className="w-5 h-5" /></button>
          <button data-testid="btn-gift" onClick={() => { setShowGifts((s) => !s); setShowEmoji(false); }} className="p-2 rounded-full hover:bg-muted"><Gift className="w-5 h-5 text-primary" /></button>
          <input
            data-testid="chat-input"
            value={text} onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && doSend()}
            placeholder="Сообщение..."
            className="flex-1 px-4 py-2 rounded-full bg-muted focus:bg-card border border-transparent focus:border-primary outline-none text-sm transition-colors duration-200"
          />
          <button data-testid="btn-send" onClick={doSend} disabled={!text.trim()} className="p-2.5 rounded-full bg-primary text-primary-foreground disabled:opacity-40 hover:opacity-90 transition-opacity duration-200"><Send className="w-4 h-4" /></button>
        </div>
      </div>
    </div>
  );
}
