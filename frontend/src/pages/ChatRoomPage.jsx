import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { createChatSocket } from "@/lib/ws";
import { useAuth } from "@/context/AuthContext";
import { ArrowLeft, Send, Smile, Gift, Languages, Reply, X, Image as ImageIcon, Mic, Video, Lock, Play, Pause, Square, Crown } from "lucide-react";
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

const readFileAsDataUrl = (file) => new Promise((resolve, reject) => {
  const fr = new FileReader();
  fr.onload = () => resolve(fr.result);
  fr.onerror = reject;
  fr.readAsDataURL(file);
});

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
  const [costs, setCosts] = useState({ costs: { text: 1, emoji: 1, image: 5, gift: 10, voice: 10, video: 15 }, free_messages: 2, is_premium: false, coins: 0 });
  const [typingPeer, setTypingPeer] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordSec, setRecordSec] = useState(0);
  const scrollRef = useRef(null);
  const socketRef = useRef(null);
  const imageInputRef = useRef(null);
  const videoInputRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const recordChunksRef = useRef([]);
  const recordTimerRef = useRef(null);
  const typingTimerRef = useRef(null);

  // Initial load + WebSocket connect
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [p, m, c] = await Promise.all([
          api.get(`/profile/${id}`),
          api.get(`/chats/${id}/messages`),
          api.get(`/chat/costs`),
        ]);
        if (cancelled) return;
        setOther(p.data);
        setMsgs(m.data || []);
        setCosts(c.data);
        setTimeout(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "instant" }), 50);
      } catch (e) {
        console.error(e);
      }
    })();

    const sock = createChatSocket({
      onMessage: (m) => {
        if (m.chat_id && (m.from_user === id || m.to_user === id)) {
          setMsgs((prev) => {
            if (prev.some((x) => x.message_id === m.message_id)) return prev;
            return [...prev, m];
          });
          setTimeout(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }), 30);
          // If this incoming message is from partner, tell them we've read it
          if (m.to_user === user?.user_id) socketRef.current?.send({ type: "read", chat_with: id });
        }
      },
      onTyping: (fromId) => {
        if (fromId === id) {
          setTypingPeer(true);
          clearTimeout(typingTimerRef.current);
          typingTimerRef.current = setTimeout(() => setTypingPeer(false), 3000);
        }
      },
      onRead: (fromId) => {
        if (fromId === id) setMsgs((prev) => prev.map((m) => (m.from_user === user?.user_id ? { ...m, read: true } : m)));
      },
    });
    socketRef.current = sock;
    return () => { cancelled = true; sock.close(); clearTimeout(typingTimerRef.current); clearInterval(recordTimerRef.current); };
    // eslint-disable-next-line
  }, [id]);

  const refreshCosts = async () => { try { const { data } = await api.get('/chat/costs'); setCosts(data); } catch { /* noop */ } };

  const send = async (payload) => {
    try {
      const { data } = await api.post(`/chats/${id}/send`, { ...payload, reply_to: reply?.message_id });
      setMsgs((prev) => (prev.some((x) => x.message_id === data.message_id) ? prev : [...prev, data]));
      setText(""); setReply(null); setShowGifts(false); setShowEmoji(false);
      refresh(); refreshCosts();
      setTimeout(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }), 30);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Ошибка");
      if (e.response?.status === 402) nav("/premium");
    }
  };

  const doSend = () => { if (text.trim()) send({ text: text.trim(), kind: "text" }); };
  const sendGift = (g) => send({ text: g.emoji, kind: "gift", gift_key: g.key });

  const uploadAndSend = async (file, kind) => {
    if (!file) return;
    // Client-side size guard mirrors backend
    const maxMb = kind === "image" ? 4 : 8;
    if (file.size > maxMb * 1024 * 1024) return toast.error(`Файл слишком большой (макс ${maxMb} МБ)`);
    setUploading(true);
    try {
      const data_url = await readFileAsDataUrl(file);
      const { data } = await api.post('/chat/media', { data_url, kind });
      await send({ kind, media_url: data.media_url });
    } catch (e) {
      toast.error(e.response?.data?.detail || "Не удалось загрузить");
    } finally { setUploading(false); }
  };

  const startRecording = async () => {
    if (recording) return;
    if (!navigator.mediaDevices?.getUserMedia) return toast.error("Микрофон недоступен");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4';
      const mr = new MediaRecorder(stream, { mimeType: mime });
      recordChunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) recordChunksRef.current.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(recordChunksRef.current, { type: mime });
        // Cap 60 sec / 8 MB
        if (blob.size > 8 * 1024 * 1024) { toast.error("Запись слишком длинная"); return; }
        const file = new File([blob], `voice-${Date.now()}.${mime.includes('webm') ? 'webm' : 'm4a'}`, { type: mime });
        await uploadAndSend(file, 'voice');
      };
      mediaRecorderRef.current = mr;
      mr.start();
      setRecording(true);
      setRecordSec(0);
      recordTimerRef.current = setInterval(() => setRecordSec((s) => {
        if (s + 1 >= 60) { stopRecording(); }
        return s + 1;
      }), 1000);
    } catch (e) {
      toast.error("Не удалось получить доступ к микрофону");
    }
  };

  const stopRecording = () => {
    clearInterval(recordTimerRef.current);
    setRecording(false);
    try { mediaRecorderRef.current?.stop(); } catch { /* noop */ }
  };
  const cancelRecording = () => {
    clearInterval(recordTimerRef.current);
    setRecording(false);
    try {
      const mr = mediaRecorderRef.current;
      mr && (mr.ondataavailable = null, mr.onstop = null, mr.stop());
    } catch { /* noop */ }
    recordChunksRef.current = [];
  };

  const translate = async (m) => {
    try {
      const { data } = await api.post("/translate", { text: m.text, target: "ru" });
      setMsgs((p) => p.map((x) => (x.message_id === m.message_id ? { ...x, translated: data.translated } : x)));
    } catch { toast.error("Не удалось перевести"); }
  };

  const translateComposer = async () => {
    if (!text.trim()) return;
    try {
      const { data } = await api.post("/translate", { text: text.trim(), target: "ru" });
      setText(data.translated);
      toast.success("Переведено");
    } catch { toast.error("Не удалось перевести"); }
  };

  const onType = () => {
    socketRef.current?.send({ type: "typing", to: id });
  };

  const nextCost = () => {
    const sentByMe = msgs.filter((m) => m.from_user === user?.user_id && (m.kind === 'text' || m.kind === 'emoji')).length;
    const withinFree = sentByMe < costs.free_messages;
    if (withinFree) return 0;
    if (costs.is_premium) return 0;
    return costs.costs.text;
  };

  return (
    <div className="min-h-screen bg-background flex justify-center">
      <div className="w-full max-w-md bg-background flex flex-col" style={{ minHeight: "100vh" }}>
        {/* Header */}
        <header className="sticky top-0 z-30 flex items-center gap-3 px-3 py-3 bg-background/90 backdrop-blur-xl border-b border-border">
          <button data-testid="chat-back" onClick={() => nav(-1)} className="p-2 -ml-2 rounded-full hover:bg-muted"><ArrowLeft className="w-5 h-5" /></button>
          {other && (
            <>
              <img src={other.photos?.[0]} alt="" className="w-10 h-10 rounded-full object-cover" />
              <div className="flex-1 min-w-0">
                <p className="font-semibold truncate">{other.name}, {other.age}</p>
                <p className="text-[11px] text-emerald-500">
                  {typingPeer ? "печатает..." : (other.online ? "онлайн" : "недавно")}
                </p>
              </div>
              <div className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="chat-coins-header">
                <span className="text-primary">💰</span>{costs.coins}
              </div>
            </>
          )}
        </header>

        {/* Message list */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-4 space-y-2" style={{ minHeight: "60vh" }}>
          {msgs.map((m) => {
            const mine = m.from_user === user?.user_id;
            const replied = m.reply_to ? msgs.find((x) => x.message_id === m.reply_to) : null;
            const locked = m.locked && !mine;
            return (
              <div key={m.message_id} data-testid={`msg-${m.message_id}`} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                <div className="max-w-[78%] group">
                  {replied && (
                    <div className={`reply-line px-2 py-1 mb-1 text-xs opacity-80 rounded ${mine ? "bg-primary/10" : "bg-muted"}`}>
                      <p className="truncate">{replied.text || replied.kind}</p>
                    </div>
                  )}
                  {locked ? (
                    <button
                      data-testid={`locked-${m.message_id}`}
                      onClick={() => nav('/premium')}
                      className="px-4 py-3 rounded-2xl bg-gradient-to-br from-primary/20 to-primary/5 border border-primary/30 text-left flex items-center gap-2"
                    >
                      <Lock className="w-4 h-4 text-primary" />
                      <span className="text-sm">Оформите Premium, чтобы прочитать</span>
                    </button>
                  ) : (
                    <div className={`px-3 py-2 rounded-2xl ${mine ? "bg-primary text-primary-foreground rounded-tr-sm" : "bg-muted text-foreground rounded-tl-sm"}`}>
                      {m.kind === "gift" ? (
                        <div className="text-center">
                          <div className="text-5xl">{m.text}</div>
                          <div className="text-[10px] mt-1 opacity-80">🎁 Подарок</div>
                        </div>
                      ) : m.kind === "image" && m.media_url ? (
                        <img src={m.media_url} alt="" className="rounded-lg max-h-64 object-cover" />
                      ) : m.kind === "voice" && m.media_url ? (
                        <audio controls src={m.media_url} className="max-w-[220px]" />
                      ) : m.kind === "video" && m.media_url ? (
                        <video controls src={m.media_url} className="rounded-lg max-h-64" />
                      ) : (
                        <p className="whitespace-pre-wrap break-words">{m.text}</p>
                      )}
                      {m.translated && <p className="mt-1 pt-1 border-t border-current/20 text-[11px] opacity-80 italic">{m.translated}</p>}
                    </div>
                  )}
                  {!locked && (
                    <div className={`flex gap-2 mt-0.5 text-[10px] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity ${mine ? "justify-end" : ""}`}>
                      <button onClick={() => setReply(m)} data-testid={`reply-${m.message_id}`}>Ответить</button>
                      {!mine && m.text && <button onClick={() => translate(m)} data-testid={`translate-${m.message_id}`}>Перевести</button>}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          {msgs.length === 0 && (
            <div className="text-center text-muted-foreground text-sm py-16">
              Первые {costs.free_messages} сообщения бесплатны.<br />Далее — {costs.costs.text}💰 текст · {costs.costs.image}💰 фото · {costs.costs.voice}💰 голос · {costs.costs.video}💰 видео · {costs.costs.gift}💰 подарок
            </div>
          )}
        </div>

        {/* Reply preview */}
        {reply && (
          <div className="px-3 py-2 flex items-center gap-2 bg-muted border-t border-border">
            <Reply className="w-4 h-4 text-muted-foreground" />
            <div className="flex-1 text-xs truncate reply-line pl-2">Ответ: {reply.text || reply.kind}</div>
            <button onClick={() => setReply(null)} data-testid="cancel-reply"><X className="w-4 h-4" /></button>
          </div>
        )}

        {/* Emoji drawer */}
        {showEmoji && (
          <div className="grid grid-cols-8 gap-1 p-3 border-t border-border bg-card max-h-40 overflow-y-auto">
            {EMOJIS.map((e) => (
              <button key={e} data-testid={`emoji-${e}`} onClick={() => send({ text: e, kind: "emoji" })} className="text-2xl hover:scale-125 transition-transform duration-200">{e}</button>
            ))}
          </div>
        )}
        {/* Gifts drawer */}
        {showGifts && (
          <div className="grid grid-cols-4 gap-2 p-3 border-t border-border bg-card">
            {GIFTS.map((g) => (
              <button key={g.key} data-testid={`gift-${g.key}`} onClick={() => sendGift(g)} className="flex flex-col items-center p-2 rounded-xl bg-muted hover:bg-primary/10 transition-colors duration-200">
                <span className="text-3xl">{g.emoji}</span>
                <span className="text-[10px] mt-1">{g.name}</span>
                <span className="text-[10px] text-primary font-bold">{costs.costs.gift} 💰</span>
              </button>
            ))}
          </div>
        )}

        {/* Recording bar */}
        {recording && (
          <div className="px-3 py-2 flex items-center gap-3 bg-red-500/10 border-t border-red-500/30" data-testid="recording-bar">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
            <span className="text-sm font-mono">{String(Math.floor(recordSec / 60)).padStart(2,'0')}:{String(recordSec % 60).padStart(2,'0')}</span>
            <span className="text-xs text-muted-foreground flex-1">Запись голосового · до 60с</span>
            <button data-testid="cancel-record" onClick={cancelRecording} className="p-2 rounded-full hover:bg-muted"><X className="w-4 h-4" /></button>
            <button data-testid="stop-record" onClick={stopRecording} className="p-2 rounded-full bg-red-500 text-white"><Square className="w-4 h-4" /></button>
          </div>
        )}

        {/* Composer */}
        <div className="sticky bottom-0 flex items-center gap-1 px-2 py-2 bg-background border-t border-border">
          <input ref={imageInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => uploadAndSend(e.target.files?.[0], 'image')} data-testid="image-input" />
          <input ref={videoInputRef} type="file" accept="video/*" className="hidden" onChange={(e) => uploadAndSend(e.target.files?.[0], 'video')} data-testid="video-input" />

          <button data-testid="btn-emoji" onClick={() => { setShowEmoji((s) => !s); setShowGifts(false); }} className="p-2 rounded-full hover:bg-muted" title={`Эмодзи · ${costs.costs.emoji}💰`}><Smile className="w-5 h-5" /></button>
          <button data-testid="btn-gift" onClick={() => { setShowGifts((s) => !s); setShowEmoji(false); }} className="p-2 rounded-full hover:bg-muted" title={`Подарок · ${costs.costs.gift}💰`}><Gift className="w-5 h-5 text-primary" /></button>
          <button data-testid="btn-image" disabled={uploading} onClick={() => imageInputRef.current?.click()} className="p-2 rounded-full hover:bg-muted disabled:opacity-40" title={`Фото · ${costs.costs.image}💰`}><ImageIcon className="w-5 h-5" /></button>
          <button data-testid="btn-voice" disabled={uploading || recording} onClick={startRecording} className="p-2 rounded-full hover:bg-muted disabled:opacity-40" title={`Голос · ${costs.costs.voice}💰`}><Mic className="w-5 h-5" /></button>
          <button data-testid="btn-video" disabled={uploading} onClick={() => videoInputRef.current?.click()} className="p-2 rounded-full hover:bg-muted disabled:opacity-40" title={`Видео · ${costs.costs.video}💰`}><Video className="w-5 h-5" /></button>

          <input
            data-testid="chat-input"
            value={text}
            onChange={(e) => { setText(e.target.value); onType(); }}
            onKeyDown={(e) => e.key === "Enter" && doSend()}
            placeholder={nextCost() > 0 ? `Сообщение · ${nextCost()}💰` : "Сообщение..."}
            className="flex-1 px-3 py-2 rounded-full bg-muted focus:bg-card border border-transparent focus:border-primary outline-none text-sm transition-colors duration-200 min-w-0"
          />
          <button data-testid="btn-translate-composer" onClick={translateComposer} disabled={!text.trim()} className="p-2 rounded-full hover:bg-muted disabled:opacity-40" title="Перевести на русский"><Languages className="w-5 h-5" /></button>
          <button data-testid="btn-send" onClick={doSend} disabled={!text.trim() || uploading} className="p-2.5 rounded-full bg-primary text-primary-foreground disabled:opacity-40 hover:opacity-90 transition-opacity duration-200"><Send className="w-4 h-4" /></button>
        </div>

        {/* Premium nudge for free users below the free window */}
        {!costs.is_premium && msgs.filter((m) => m.from_user !== user?.user_id).some((m) => m.locked) && (
          <button onClick={() => nav('/premium')} data-testid="premium-nudge" className="mx-3 mb-3 flex items-center justify-center gap-2 py-2 rounded-full bg-gradient-to-r from-primary to-fuchsia-500 text-primary-foreground text-sm font-semibold">
            <Crown className="w-4 h-4" /> Оформить Premium
          </button>
        )}
      </div>
    </div>
  );
}
