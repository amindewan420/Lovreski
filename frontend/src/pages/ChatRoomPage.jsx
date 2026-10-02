import { useEffect, useRef, useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { createChatSocket } from "@/lib/ws";
import { useAuth } from "@/context/AuthContext";
import { useI18n, getLangMeta } from "@/lib/i18n";
import EmojiPanel from "@/components/lovreski/EmojiPanel";
import GiftPanel from "@/components/lovreski/GiftPanel";
import LanguageSheet from "@/components/lovreski/LanguageSheet";
import {
  ArrowLeft, Send, Plus, Image as ImageIcon, File as FileIcon, Video, Mic, Square,
  Smile, Gift, Globe, Reply, X, Check, CheckCheck, Lock, ShoppingBag, Trash2, MapPin, ChevronDown,
} from "lucide-react";
import { toast } from "sonner";

// ─── Helpers ───────────────────────────────────────────────────────────────
const pad = (n) => String(n).padStart(2, "0");
const fmtTime = (iso) => { const d = new Date(iso); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
const RU_MONTHS = ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"];
function dateLabel(iso, t) {
  const d = new Date(iso); const now = new Date();
  const yest = new Date(now); yest.setDate(now.getDate() - 1);
  if (sameDay(d, now)) return t("chat.today");
  if (sameDay(d, yest)) return t("chat.yesterday");
  return `${d.getDate()} ${RU_MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}
const readFileAsDataUrl = (file) => new Promise((res, rej) => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.onerror = rej; fr.readAsDataURL(file); });

// ─── Main ──────────────────────────────────────────────────────────────────
export default function ChatRoomPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user, refresh } = useAuth();
  const { t, lang, setLang } = useI18n();
  const langMeta = getLangMeta(lang);

  const [other, setOther] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const [reply, setReply] = useState(null);
  const [status, setStatus] = useState({ sent_count: 0, free_used: 0, free_limit: 2, coins: 0, is_premium: false, is_blocked: false });
  const [typingPeer, setTypingPeer] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordSec, setRecordSec] = useState(0);

  // Sheets / modals
  const [showTray, setShowTray] = useState(false);
  const [showEmoji, setShowEmoji] = useState(false);
  const [showGifts, setShowGifts] = useState(false);
  const [showLang, setShowLang] = useState(false);
  const [showBlockPopup, setShowBlockPopup] = useState(false);
  const [actionTarget, setActionTarget] = useState(null);   // message-action sheet (Reply / Delete)
  const longPressTimerRef = useRef(null);
  const [showScrollDown, setShowScrollDown] = useState(false);

  // Swipe-to-reply state
  const [swipeState, setSwipeState] = useState({ id: null, dx: 0 });
  const swipeRef = useRef({ startX: 0, startY: 0, id: null, active: false, locked: null });
  const [highlightId, setHighlightId] = useState(null);
  const highlightTimerRef = useRef(null);

  const scrollRef = useRef(null);
  const socketRef = useRef(null);
  const inputRef = useRef(null);
  const textareaRef = useRef(null);
  const imgRef = useRef(null);
  const vidRef = useRef(null);
  const fileRef = useRef(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const recordTimerRef = useRef(null);
  const typingTimerRef = useRef(null);

  // ─── Initial load + WS ───────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [p, m, s] = await Promise.all([
          api.get(`/profile/${id}`),
          api.get(`/chats/${id}/messages`),
          api.get(`/chat/status/${id}`),
        ]);
        if (cancelled) return;
        setOther(p.data);
        setMsgs(m.data || []);
        setStatus(s.data);
        scrollBottom(true);
      } catch (e) { /* noop */ }
    })();
    const sock = createChatSocket({
      onMessage: (m) => {
        if (m.chat_id && (m.from_user === id || m.to_user === id)) {
          setMsgs((prev) => prev.some((x) => x.message_id === m.message_id) ? prev : [...prev, m]);
          scrollBottom();
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
        if (fromId === id) setMsgs((prev) => prev.map((m) => m.from_user === user?.user_id ? { ...m, read: true } : m));
      },
      onDeleted: (info) => {
        // Tombstone the message locally so all viewers see the placeholder instantly.
        setMsgs((prev) => prev.map((m) => m.message_id === info.message_id
          ? { ...m, deleted: true, text: "", media_url: null, file_name: null, gift_key: null }
          : m));
      },
    });
    socketRef.current = sock;
    return () => { cancelled = true; sock.close(); clearTimeout(typingTimerRef.current); clearInterval(recordTimerRef.current); };
    // eslint-disable-next-line
  }, [id]);

  const scrollBottom = (instant = false) => setTimeout(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: instant ? "instant" : "smooth" }), 40);
  const refreshStatus = async () => { try { const { data } = await api.get(`/chat/status/${id}`); setStatus(data); } catch { /* noop */ } };

  // ─── Send ────────────────────────────────────────────────────────────
  const send = async (payload) => {
    try {
      const { data } = await api.post(`/chats/${id}/send`, { ...payload, reply_to: reply?.message_id });
      setMsgs((prev) => prev.some((x) => x.message_id === data.message_id) ? prev : [...prev, data]);
      setText(""); setReply(null); setShowGifts(false); setShowEmoji(false); setShowTray(false);
      refresh(); refreshStatus();
      scrollBottom();
    } catch (e) {
      const detail = e.response?.data?.detail;
      const isBlocked = typeof detail === 'object' && detail?.blocked;
      if (isBlocked || e.response?.status === 402) { setShowBlockPopup(true); refreshStatus(); return; }
      toast.error(typeof detail === 'string' ? detail : (detail?.message || t("common.error")));
    }
  };
  const doSend = () => { if (text.trim() && !status.is_blocked) send({ text: text.trim(), kind: "text" }); };
  const sendEmoji = (e) => send({ text: e, kind: "emoji" });
  const sendGift = (g) => send({ text: g.emoji, kind: "gift", gift_key: g.key });

  // ─── Media upload ────────────────────────────────────────────────────
  const uploadAndSend = async (file, kind) => {
    if (!file) return;
    const maxMb = kind === 'image' ? 4 : 10;
    if (file.size > maxMb * 1024 * 1024) return toast.error(`Файл слишком большой (макс ${maxMb} МБ)`);
    setUploading(true);
    try {
      const data_url = await readFileAsDataUrl(file);
      const { data } = await api.post('/chat/media', { data_url, kind, file_name: file.name });
      await send({ kind, media_url: data.media_url, file_name: file.name, text: kind === 'file' ? file.name : "" });
    } catch (e) {
      toast.error(e.response?.data?.detail || t("common.error"));
    } finally { setUploading(false); }
  };
  const startRecording = async () => {
    if (recording || status.is_blocked) return;
    if (!navigator.mediaDevices?.getUserMedia) return toast.error("Микрофон недоступен");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4';
      const mr = new MediaRecorder(stream, { mimeType: mime });
      chunksRef.current = [];
      mr.ondataavailable = (e) => e.data.size > 0 && chunksRef.current.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: mime });
        if (blob.size > 8 * 1024 * 1024) return toast.error("Запись слишком длинная");
        const file = new File([blob], `voice-${Date.now()}.${mime.includes('webm') ? 'webm' : 'm4a'}`, { type: mime });
        await uploadAndSend(file, 'voice');
      };
      recorderRef.current = mr; mr.start();
      setRecording(true); setRecordSec(0);
      recordTimerRef.current = setInterval(() => setRecordSec((s) => { if (s + 1 >= 60) stopRecording(); return s + 1; }), 1000);
    } catch { toast.error("Не удалось получить доступ к микрофону"); }
  };
  const stopRecording = () => { clearInterval(recordTimerRef.current); setRecording(false); try { recorderRef.current?.stop(); } catch { /* noop */ } };
  const cancelRecording = () => { clearInterval(recordTimerRef.current); setRecording(false); try { const mr = recorderRef.current; if (mr) { mr.ondataavailable = null; mr.onstop = null; mr.stop(); } } catch { /* noop */ } chunksRef.current = []; };

  // ─── Translate ───────────────────────────────────────────────────────
  const translate = async (m) => {
    try {
      const { data } = await api.post('/translate', { text: m.text, target: lang });
      setMsgs((p) => p.map((x) => x.message_id === m.message_id ? { ...x, translated: data.translated } : x));
    } catch { toast.error("Не удалось перевести"); }
  };

  // ─── Delete ──────────────────────────────────────────────────────────
  const doDelete = async (scope) => {
    if (!actionTarget) return;
    const m = actionTarget;
    setActionTarget(null);
    try {
      await api.delete(`/messages/${m.message_id}?scope=${scope}`);
      if (scope === "everyone") {
        // WS will broadcast to both — but update ours immediately for snappiness.
        setMsgs((prev) => prev.map((x) => x.message_id === m.message_id
          ? { ...x, deleted: true, text: "", media_url: null, file_name: null, gift_key: null } : x));
      } else {
        setMsgs((prev) => prev.filter((x) => x.message_id !== m.message_id));
      }
      toast.success(t("chat.deleted"));
    } catch (e) {
      toast.error(e.response?.data?.detail || t("common.error"));
    }
  };

  const canDeleteEveryone = (m) => {
    if (!user) return false;
    if (m.from_user !== user.user_id && !user.is_admin) return false;
    if (m.deleted) return false;
    if (user.is_admin) return true;
    const age = (Date.now() - new Date(m.created_at).getTime()) / 1000;
    return age <= 3600;
  };

  const startLongPress = (m) => {
    clearTimeout(longPressTimerRef.current);
    longPressTimerRef.current = setTimeout(() => {
      if (!m.deleted) { setActionTarget(m); navigator.vibrate?.(15); }
    }, 550);
  };
  const cancelLongPress = () => { clearTimeout(longPressTimerRef.current); };

  // ─── Swipe-right to reply ─────────────────────────────────────────────
  const onMsgTouchStart = (m) => (e) => {
    if (m.deleted) return;
    const t0 = e.touches[0];
    swipeRef.current = { startX: t0.clientX, startY: t0.clientY, id: m.message_id, active: true, locked: null };
  };
  const onMsgTouchMove = (m) => (e) => {
    const s = swipeRef.current;
    if (!s.active || s.id !== m.message_id) return;
    const t0 = e.touches[0];
    const dx = t0.clientX - s.startX;
    const dy = t0.clientY - s.startY;
    // Decide gesture axis once, then stick with it (avoids fighting vertical scroll)
    if (s.locked === null) {
      if (Math.abs(dx) < 6 && Math.abs(dy) < 6) return;
      s.locked = Math.abs(dx) > Math.abs(dy) ? "x" : "y";
    }
    if (s.locked !== "x") return;
    if (dx < 0) { setSwipeState({ id: m.message_id, dx: 0 }); return; } // only right-swipe
    cancelLongPress(); // moving cancels long-press intent
    const clamped = Math.min(dx, 90);
    setSwipeState({ id: m.message_id, dx: clamped });
  };
  const onMsgTouchEnd = (m) => () => {
    const s = swipeRef.current;
    if (!s.active || s.id !== m.message_id) { setSwipeState({ id: null, dx: 0 }); return; }
    const dx = swipeState.id === m.message_id ? swipeState.dx : 0;
    swipeRef.current.active = false;
    if (dx > 55 && !m.deleted) {
      setReply(m);
      navigator.vibrate?.(15);
    }
    setSwipeState({ id: null, dx: 0 });
  };

  // ─── Scroll to (and highlight) a specific message ─────────────────────
  const scrollToMessage = (mid) => {
    const el = document.getElementById(`m-${mid}`);
    if (!el) { toast(t("chat.original_deleted")); return; }
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    clearTimeout(highlightTimerRef.current);
    setHighlightId(mid);
    highlightTimerRef.current = setTimeout(() => setHighlightId(null), 1200);
  };

  // ─── Scroll-to-bottom FAB ─────────────────────────────────────────────
  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollDown(distanceFromBottom > 120);
  };

  // ─── Location share (browser Geolocation → OpenStreetMap link) ───────
  const shareLocation = () => {
    setShowTray(false);
    if (!navigator.geolocation) return toast.error("Геолокация недоступна");
    toast.loading("Определяем местоположение...", { id: "geo" });
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        toast.dismiss("geo");
        const { latitude, longitude } = pos.coords;
        const url = `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=17/${latitude}/${longitude}`;
        send({ kind: "text", text: `📍 ${url}` });
      },
      (err) => {
        toast.dismiss("geo");
        toast.error(err.code === 1 ? "Доступ к геолокации запрещён" : "Не удалось определить местоположение");
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  // ─── Input auto-grow + typing broadcast ──────────────────────────────
  const onInput = (e) => {
    setText(e.target.value);
    socketRef.current?.send({ type: "typing", to: id });
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  };

  // ─── Group messages with date separators ─────────────────────────────
  const grouped = useMemo(() => {
    const out = []; let lastDate = null;
    for (const m of msgs) {
      const d = new Date(m.created_at);
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      if (key !== lastDate) { out.push({ type: 'sep', id: `sep-${key}`, iso: m.created_at }); lastDate = key; }
      out.push({ type: 'msg', id: m.message_id, m });
    }
    return out;
  }, [msgs]);

  const blocked = status.is_blocked && !status.is_premium;

  // ─── Render ──────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-white flex justify-center">
      <div className="w-full max-w-md bg-white flex flex-col relative" style={{ height: "100dvh" }}>
        {/* Header */}
        <header className="sticky top-0 z-30 flex items-center gap-3 px-3 py-2.5 bg-white border-b border-slate-200">
          <button data-testid="chat-back" onClick={() => nav(-1)} className="p-2 -ml-2 rounded-full hover:bg-slate-100"><ArrowLeft className="w-5 h-5 text-slate-700" /></button>
          {other && (
            <>
              <div className="relative">
                <img src={other.photos?.[0]} alt="" className="w-10 h-10 rounded-full object-cover" />
                {other.online && <span className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-emerald-500 border-2 border-white" />}
              </div>
              <div className="flex-1 min-w-0" onClick={() => nav(`/profile/${other.user_id}`)}>
                <p className="font-semibold text-slate-900 truncate no-translate">{other.name}, {other.age}</p>
                <p className="text-[11px] text-emerald-600">
                  {typingPeer ? t("chat.typing") : (other.online ? t("chat.online") : t("chat.recent"))}
                </p>
              </div>
              <div data-testid="chat-coins-header" className="flex items-center gap-1 text-xs text-slate-600 bg-slate-100 px-2 py-1 rounded-full">
                <span>💰</span><span className="font-semibold">{status.coins}</span>
              </div>
            </>
          )}
        </header>

        {/* Message list */}
        <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto px-3 py-4 space-y-1.5 bg-white">
          {grouped.map((row) => row.type === 'sep' ? (
            <div key={row.id} className="flex justify-center py-2" data-testid={`date-sep-${row.id}`}>
              <span className="text-[11px] font-medium px-3 py-1 rounded-full bg-slate-100 text-slate-600">{dateLabel(row.iso, t)}</span>
            </div>
          ) : (() => {
            const m = row.m; const mine = m.from_user === user?.user_id;
            const replied = m.reply_to ? msgs.find((x) => x.message_id === m.reply_to) : null;
            const locked = m.locked && !mine;
            const canLongPress = !m.deleted;
            const swiping = swipeState.id === m.message_id;
            const dx = swiping ? swipeState.dx : 0;
            const showHint = swiping && dx > 8;
            const highlighted = highlightId === m.message_id;
            const repliedSenderName = replied
              ? (replied.from_user === user?.user_id ? t("chat.you") : (other?.name || ""))
              : "";
            const repliedSnippet = replied
              ? (replied.text || {
                  image: "🖼 " + t("chat.gift_gallery"),
                  video: "🎬 " + t("chat.gift_camera"),
                  voice: "🎤 " + (t("chat.recording") || ""),
                  file: "📎 " + (replied.file_name || t("chat.gift_file")),
                  gift: "🎁",
                  emoji: replied.text,
                }[replied.kind] || replied.kind)
              : "";
            return (
              <div
                key={m.message_id}
                id={`m-${m.message_id}`}
                data-testid={`msg-${m.message_id}`}
                className={`chat-msg-row flex relative ${mine ? "justify-end" : "justify-start"} ${highlighted ? "chat-msg-flash" : ""}`}
                style={{ transform: dx ? `translateX(${dx}px)` : undefined }}
                onTouchStart={onMsgTouchStart(m)}
                onTouchMove={onMsgTouchMove(m)}
                onTouchEnd={onMsgTouchEnd(m)}
                onTouchCancel={onMsgTouchEnd(m)}
              >
                {showHint && (
                  <div
                    className="swipe-reply-hint"
                    style={{ left: 4, opacity: Math.min(1, dx / 55) }}
                    data-testid={`swipe-hint-${m.message_id}`}
                  >
                    <Reply className="w-4 h-4" />
                  </div>
                )}
                <div className="max-w-[78%] group">
                  {replied && (
                    <button
                      type="button"
                      onClick={() => scrollToMessage(replied.message_id)}
                      data-testid={`quoted-${m.message_id}`}
                      className={`w-full text-left px-2.5 py-1.5 mb-1 rounded-lg border-l-[3px] active:opacity-70 transition ${
                        mine ? "bg-sky-50/80 border-sky-500" : "bg-slate-100 border-emerald-500"
                      }`}
                    >
                      {replied.deleted ? (
                        <p className="italic opacity-70 text-[11px] text-slate-500">{t("chat.original_deleted")}</p>
                      ) : (
                        <>
                          <p className={`text-[11px] font-semibold leading-tight ${mine ? "text-sky-700" : "text-emerald-700"} no-translate`}>
                            {repliedSenderName}
                          </p>
                          <p className="text-[12px] text-slate-600 leading-snug line-clamp-2 no-translate">
                            {repliedSnippet}
                          </p>
                        </>
                      )}
                    </button>
                  )}
                  {locked ? (
                    <button data-testid={`locked-${m.message_id}`} onClick={() => nav('/premium')}
                      className="px-4 py-3 rounded-2xl bg-gradient-to-br from-primary/15 to-primary/5 border border-primary/30 text-left flex items-center gap-2">
                      <Lock className="w-4 h-4 text-primary" />
                      <span className="text-sm text-slate-700">{t("chat.premium_locked")}</span>
                    </button>
                  ) : m.deleted ? (
                    <div
                      data-testid={`deleted-${m.message_id}`}
                      className={`px-3 py-2 rounded-2xl italic text-[13px] flex items-center gap-1.5 ${
                        mine ? "bg-sky-50 text-slate-500 border border-sky-100" : "bg-slate-50 text-slate-500 border border-slate-200"
                      }`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      <span>{t("chat.deleted")}</span>
                      <span className="text-[10px] not-italic ml-2 text-slate-400">{fmtTime(m.created_at)}</span>
                    </div>
                  ) : (
                    <div
                      onMouseDown={canLongPress ? () => startLongPress(m) : undefined}
                      onMouseUp={cancelLongPress}
                      onMouseLeave={cancelLongPress}
                      onTouchStart={canLongPress ? () => startLongPress(m) : undefined}
                      onTouchEnd={cancelLongPress}
                      onContextMenu={canLongPress ? (e) => { e.preventDefault(); setActionTarget(m); } : undefined}
                      className={`relative px-3 py-2 rounded-2xl shadow-sm ${
                        mine
                          ? "bg-[#DCF2FF] text-slate-900 rounded-br-md"
                          : "bg-white text-slate-900 rounded-bl-md border border-slate-200"
                      }`}
                    >
                      {m.kind === "gift" ? (
                        <div className="text-center py-1">
                          <div className="text-5xl">{m.text}</div>
                          <div className="text-[10px] mt-1 text-slate-500">{t("chat.preview_gift")}</div>
                        </div>
                      ) : m.kind === "image" && m.media_url ? (
                        <img src={m.media_url} alt="" className="rounded-lg max-h-64 object-cover" />
                      ) : m.kind === "voice" && m.media_url ? (
                        <audio controls src={m.media_url} className="max-w-[220px]" />
                      ) : m.kind === "video" && m.media_url ? (
                        <video controls src={m.media_url} className="rounded-lg max-h-64" />
                      ) : m.kind === "file" && m.media_url ? (
                        <a href={m.media_url} download={m.file_name || "file"} className="flex items-center gap-2 text-sm">
                          <FileIcon className="w-5 h-5" />
                          <span className="underline truncate max-w-[180px] no-translate">{m.file_name || "file"}</span>
                        </a>
                      ) : (
                        <p className="whitespace-pre-wrap break-words text-[15px] leading-snug no-translate">{m.text}</p>
                      )}
                      {m.translated && <p className="mt-1 pt-1 border-t border-slate-200 text-[12px] text-slate-500 italic no-translate">{m.translated}</p>}
                      <div className="flex items-center justify-end gap-1 mt-0.5 text-[10px] text-slate-500">
                        <span>{fmtTime(m.created_at)}</span>
                        {mine && (m.read ? <CheckCheck className="w-3.5 h-3.5 text-sky-500" /> : <Check className="w-3.5 h-3.5" />)}
                      </div>
                    </div>
                  )}
                  {!locked && !m.deleted && (
                    <div className={`flex gap-2 mt-0.5 text-[10px] text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity ${mine ? "justify-end" : ""}`}>
                      <button onClick={() => setReply(m)} data-testid={`reply-${m.message_id}`}>{t("chat.reply")}</button>
                      {!mine && m.text && <button onClick={() => translate(m)} data-testid={`translate-${m.message_id}`}>{t("chat.translate")}</button>}
                      {(mine || user?.is_admin) && <button onClick={() => setActionTarget(m)} data-testid={`delete-${m.message_id}`}>{t("chat.delete_me")}</button>}
                    </div>
                  )}
                </div>
              </div>
            );
          })())}
          {msgs.length === 0 && (
            <div className="text-center text-slate-400 text-sm py-16 px-4">
              Первые {status.free_limit} сообщения бесплатны.
            </div>
          )}
        </div>

        {/* Reply preview — WhatsApp-style slide-up above the composer */}
        {reply && (() => {
          const replyMine = reply.from_user === user?.user_id;
          const senderName = replyMine ? t("chat.you") : (other?.name || "");
          const snippet = reply.text || {
            image: "🖼 " + t("chat.gift_gallery"),
            video: "🎬 " + t("chat.gift_camera"),
            voice: "🎤 " + t("chat.recording"),
            file: "📎 " + (reply.file_name || t("chat.gift_file")),
            gift: "🎁 " + t("chat.preview_gift"),
            emoji: reply.text,
          }[reply.kind] || reply.kind;
          return (
            <div
              className="px-3 py-2 bg-slate-50 border-t border-slate-200 overflow-hidden"
              style={{ animation: "chatReplyBarIn 200ms cubic-bezier(0.2,0.9,0.3,1)" }}
              data-testid="reply-preview"
            >
              <div className={`flex items-start gap-2 rounded-lg px-3 py-2 border-l-[4px] bg-white ${replyMine ? "border-sky-500" : "border-emerald-500"}`}>
                <Reply className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className={`text-[12px] font-semibold leading-tight no-translate ${replyMine ? "text-sky-700" : "text-emerald-700"}`}>
                    {senderName}
                  </p>
                  <p className="text-[13px] text-slate-600 leading-snug line-clamp-2 no-translate">{snippet}</p>
                </div>
                <button
                  onClick={() => setReply(null)}
                  data-testid="cancel-reply"
                  aria-label={t("chat.cancel")}
                  className="p-1 -mr-1 rounded-full hover:bg-slate-100 shrink-0"
                >
                  <X className="w-4 h-4 text-slate-500" />
                </button>
              </div>
            </div>
          );
        })()}

        {/* Recording bar */}
        {recording && (
          <div className="px-3 py-2 flex items-center gap-3 bg-red-50 border-t border-red-200" data-testid="recording-bar">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
            <span className="text-sm font-mono text-slate-700">{pad(Math.floor(recordSec / 60))}:{pad(recordSec % 60)}</span>
            <span className="text-xs text-slate-500 flex-1">{t("chat.recording")}</span>
            <button data-testid="cancel-record" onClick={cancelRecording} className="p-2 rounded-full hover:bg-red-100"><X className="w-4 h-4 text-slate-600" /></button>
            <button data-testid="stop-record" onClick={stopRecording} className="p-2 rounded-full bg-red-500 text-white"><Square className="w-4 h-4" /></button>
          </div>
        )}

        {/* Composer */}
        <div className="sticky bottom-0 flex items-end gap-2 px-3 py-2 bg-white border-t border-slate-200">
          <input ref={imgRef} type="file" accept="image/*" className="hidden" onChange={(e) => uploadAndSend(e.target.files?.[0], 'image')} data-testid="image-input" />
          <input ref={vidRef} type="file" accept="video/*" className="hidden" onChange={(e) => uploadAndSend(e.target.files?.[0], 'video')} data-testid="video-input" />
          <input ref={fileRef} type="file" className="hidden" onChange={(e) => uploadAndSend(e.target.files?.[0], 'file')} data-testid="file-input" />

          <button
            data-testid="btn-plus"
            onClick={() => { if (blocked) { setShowBlockPopup(true); return; } setShowTray((s) => !s); setShowEmoji(false); setShowGifts(false); }}
            className={`p-2.5 rounded-full ${showTray ? "bg-primary text-primary-foreground rotate-45" : "hover:bg-slate-100 text-slate-600"} transition-transform`}
          >
            <Plus className="w-5 h-5" />
          </button>

          <div className="flex-1 min-w-0 bg-slate-100 rounded-3xl px-3 py-1.5" onClick={() => blocked && setShowBlockPopup(true)}>
            <textarea
              ref={textareaRef}
              data-testid="chat-input"
              value={text}
              onChange={onInput}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); doSend(); } }}
              placeholder={blocked ? t("chat.placeholder_blocked") : t("chat.placeholder")}
              readOnly={blocked}
              rows={1}
              className={`w-full bg-transparent outline-none text-[15px] resize-none leading-6 ${blocked ? "text-slate-400 cursor-not-allowed" : "text-slate-900"}`}
              style={{ maxHeight: 120 }}
            />
          </div>

          {recording ? null : (
            text.trim() ? (
              <button data-testid="btn-send" onClick={doSend} disabled={blocked} className="p-2.5 rounded-full bg-primary text-primary-foreground disabled:opacity-40 active:scale-95 transition">
                <Send className="w-4 h-4" />
              </button>
            ) : (
              <button data-testid="btn-mic" onClick={() => blocked ? setShowBlockPopup(true) : startRecording()} className="p-2.5 rounded-full hover:bg-slate-100 text-slate-600">
                <Mic className="w-5 h-5" />
              </button>
            )
          )}
        </div>

        {/* Scroll-to-bottom floating button — appears when scrolled up */}
        {showScrollDown && (
          <button
            data-testid="scroll-to-bottom"
            onClick={() => scrollBottom()}
            aria-label="К последним сообщениям"
            className="absolute right-4 bottom-24 z-20 w-11 h-11 rounded-full bg-white shadow-lg border border-slate-200 flex items-center justify-center text-slate-600 hover:bg-slate-50 active:scale-90 transition-transform"
            style={{ animation: "chatFabIn 180ms ease-out" }}
          >
            <ChevronDown className="w-5 h-5" />
          </button>
        )}

        {/* Attachment sheet — WhatsApp-style slide-up modal with backdrop */}
        {showTray && !blocked && (
          <div className="fixed inset-0 z-[60]" data-testid="attach-tray" onClick={() => setShowTray(false)}>
            <div className="absolute inset-0 bg-black/40" style={{ animation: "chatBackdropIn 180ms ease-out" }} />
            <div
              onClick={(e) => e.stopPropagation()}
              className="absolute bottom-0 left-1/2 -translate-x-1/2 w-full max-w-md bg-white rounded-t-3xl shadow-2xl"
              style={{ animation: "chatSheetIn 220ms cubic-bezier(0.2,0.9,0.3,1)" }}
            >
              <div className="flex items-center justify-between px-4 pt-4 pb-1">
                <p className="text-sm font-semibold text-slate-700">Прикрепить</p>
                <button data-testid="tray-close" onClick={() => setShowTray(false)} className="p-1.5 rounded-full hover:bg-slate-100"><X className="w-4 h-4 text-slate-500" /></button>
              </div>
              {/* Drag handle */}
              <div className="mx-auto w-10 h-1 rounded-full bg-slate-200 mb-3" />
              <div className="grid grid-cols-4 gap-y-5 gap-x-2 px-4 pb-6">
                <TrayBtn testid="tray-gallery" label={t("chat.gift_gallery")}   onClick={() => { setShowTray(false); imgRef.current?.click(); }} bg="bg-violet-100 text-violet-600"><ImageIcon className="w-6 h-6" /></TrayBtn>
                <TrayBtn testid="tray-video"   label={t("chat.gift_camera")}    onClick={() => { setShowTray(false); vidRef.current?.click(); }} bg="bg-emerald-100 text-emerald-600"><Video className="w-6 h-6" /></TrayBtn>
                <TrayBtn testid="tray-file"    label={t("chat.gift_file")}      onClick={() => { setShowTray(false); fileRef.current?.click(); }} bg="bg-blue-100 text-blue-600"><FileIcon className="w-6 h-6" /></TrayBtn>
                <TrayBtn testid="tray-location" label="Локация"                 onClick={shareLocation} bg="bg-rose-100 text-rose-600"><MapPin className="w-6 h-6" /></TrayBtn>
                <TrayBtn testid="tray-emoji"   label={t("chat.gift_emoji")}     onClick={() => { setShowTray(false); setShowEmoji(true); }} bg="bg-amber-100 text-amber-600"><Smile className="w-6 h-6" /></TrayBtn>
                <TrayBtn testid="tray-gifts"   label={t("chat.gift_gifts")}     onClick={() => { setShowTray(false); setShowGifts(true); }} bg="bg-pink-100 text-pink-600"><Gift className="w-6 h-6" /></TrayBtn>
                <TrayBtn testid="tray-lang"    label={t("chat.gift_translate")} onClick={() => { setShowTray(false); setShowLang(true); }} bg="bg-cyan-100 text-cyan-600"><Globe className="w-6 h-6" /></TrayBtn>
              </div>
            </div>
          </div>
        )}

        {/* Bottom sheets */}
        <EmojiPanel open={showEmoji} onClose={() => setShowEmoji(false)} onPick={(e) => { setShowEmoji(false); sendEmoji(e); }} />
        <GiftPanel open={showGifts} onClose={() => setShowGifts(false)} onSend={sendGift} coins={status.coins} />
        <LanguageSheet open={showLang} onClose={() => setShowLang(false)} onSelect={async (l) => { const r = await setLang(l.code); setShowLang(false); if (r?.actualLang !== l.code) toast.error("Перевод недоступен, оставили русский"); else toast.success(`${l.flag} ${l.name}`); }} />

        {/* Block popup */}
        {showBlockPopup && (
          <div className="fixed inset-0 z-[80] flex items-center justify-center px-4" data-testid="block-popup">
            <div className="absolute inset-0 bg-black/60" onClick={() => setShowBlockPopup(false)} />
            <div className="relative bg-white rounded-3xl w-full max-w-xs p-6 text-center">
              <div className="mx-auto w-16 h-16 rounded-full bg-primary/15 flex items-center justify-center mb-3">
                <Lock className="w-7 h-7 text-primary" />
              </div>
              <p className="font-bold text-slate-900 text-lg leading-snug">{t("chat.limit_title")}</p>
              <p className="text-sm text-slate-500 mt-2">{t("chat.limit_body")}</p>
              <div className="mt-4 text-left space-y-1 text-xs text-slate-600 bg-slate-50 rounded-xl p-3">
                <p className="font-semibold text-slate-800 mb-1">💰 Тарифы:</p>
                <p>100 монет — 500 ₽</p>
                <p>200 монет — 900 ₽</p>
                <p>300 монет — 1 200 ₽</p>
                <p>500 монет — 1 900 ₽</p>
              </div>
              <button data-testid="popup-buy" onClick={() => { setShowBlockPopup(false); nav('/premium'); }} className="mt-4 w-full py-3 rounded-full bg-primary text-primary-foreground font-semibold flex items-center justify-center gap-2">
                <ShoppingBag className="w-4 h-4" /> {t("chat.buy_coins")}
              </button>
              <button data-testid="popup-close" onClick={() => setShowBlockPopup(false)} className="mt-2 w-full py-2 text-sm text-slate-500">{t("chat.close")}</button>
            </div>
          </div>
        )}

        {/* Message actions sheet — Reply / Delete for me / Delete for everyone */}
        {actionTarget && (
          <div className="fixed inset-0 z-[80] flex items-end sm:items-center sm:justify-center px-4" data-testid="action-sheet">
            <div className="absolute inset-0 bg-black/60" onClick={() => setActionTarget(null)} />
            <div className="relative bg-white rounded-t-3xl sm:rounded-3xl w-full sm:max-w-xs p-5" style={{ animation: "chatSheetIn 220ms cubic-bezier(0.2,0.9,0.3,1)" }}>
              <div className="mx-auto w-10 h-1 rounded-full bg-slate-200 mb-3 sm:hidden" />
              <button
                data-testid="action-reply-btn"
                onClick={() => { const m = actionTarget; setActionTarget(null); setReply(m); }}
                className="w-full py-3 rounded-2xl bg-primary/10 text-primary font-semibold text-sm mb-2 flex items-center justify-center gap-2"
              >
                <Reply className="w-4 h-4" /> {t("chat.reply")}
              </button>
              {(actionTarget.from_user === user?.user_id || user?.is_admin) && (
                <>
                  <button data-testid="delete-me-btn" onClick={() => doDelete("me")} className="w-full py-3 rounded-2xl bg-slate-100 text-slate-800 font-medium text-sm mb-2 flex items-center justify-center gap-2">
                    <Trash2 className="w-4 h-4" /> {t("chat.delete_me")}
                  </button>
                  {canDeleteEveryone(actionTarget) && (
                    <button data-testid="delete-everyone-btn" onClick={() => doDelete("everyone")} className="w-full py-3 rounded-2xl bg-red-500 text-white font-semibold text-sm mb-2 flex items-center justify-center gap-2">
                      <Trash2 className="w-4 h-4" /> {t("chat.delete_everyone")}
                    </button>
                  )}
                </>
              )}
              <button data-testid="action-cancel" onClick={() => setActionTarget(null)} className="w-full py-2 text-sm text-slate-500">{t("chat.cancel")}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const TrayBtn = ({ testid, label, onClick, bg, children }) => (
  <button data-testid={testid} onClick={onClick} className="flex flex-col items-center gap-1.5">
    <div className={`w-12 h-12 rounded-2xl flex items-center justify-center ${bg}`}>{children}</div>
    <span className="text-[10px] text-slate-600 font-medium">{label}</span>
  </button>
);
