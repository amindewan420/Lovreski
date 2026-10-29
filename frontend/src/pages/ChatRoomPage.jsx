import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { useContentTx } from "@/lib/contentTranslate";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { createChatSocket } from "@/lib/ws";
import { useAuth } from "@/context/AuthContext";
import { useI18n, getLangMeta } from "@/lib/i18n";
import EmojiPanel from "@/components/lovreski/EmojiPanel";
import GiftPanel from "@/components/lovreski/GiftPanel";
import LanguageSheet from "@/components/lovreski/LanguageSheet";
import { LocationPicker, LocationBubble } from "@/components/lovreski/LocationShare";
import { useChatTranslation } from "@/hooks/useChatTranslation";
import { startLiveShare } from "@/lib/liveLocation";
import { MessageActionSheet, SelectionBar, BulkDeleteDialog } from "@/components/lovreski/MessageActions";
import { ChatMediaViewer, isPdfMsg, downloadChatMedia } from "@/components/lovreski/ChatMediaViewer";
import {
  ArrowLeft, Send, Plus, Image as ImageIcon, File as FileIcon, Video, Mic, Square,
  Smile, Gift, Globe, Reply, X, Check, CheckCheck, Lock, ShoppingBag, Trash2, MapPin, ChevronDown, Download,
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

// ─── Signed media URL with silent re-minting ──────────────────────────────
// Signed URLs expire after 10 min. This hook proactively re-mints every 8 min
// and also retries once when the media element errors (403 → expired sig).
const FILE_ID_RE = /\/api\/files\/([0-9a-f]{24})/;
const useSignedMediaUrl = (url) => {
  const [src, setSrc] = useState(url);
  const idRef = useRef(null);
  useEffect(() => { idRef.current = url?.match(FILE_ID_RE)?.[1] || null; setSrc(url); }, [url]);
  const remint = async () => {
    const fid = idRef.current;
    if (!fid) return;
    try {
      const { data } = await api.get(`/files/${fid}/signed`);
      if (data?.url) setSrc(data.url);
    } catch { /* noop — keep current src */ }
  };
  useEffect(() => {
    if (!idRef.current) return;
    const t = setInterval(remint, 8 * 60 * 1000);
    return () => clearInterval(t);
    // eslint-disable-next-line
  }, [url]);
  return [src, remint];
};

const MediaBubble = ({ m, onOpen, t }) => {
  const [src, onErr] = useSignedMediaUrl(m.media_url);
  if (m.kind === "image") {
    return (
      <button type="button" onClick={() => onOpen(m)} className="block cursor-zoom-in" data-testid={`media-open-${m.message_id}`}>
        <img src={src} onError={onErr} alt="" className="rounded-lg max-h-64 object-cover" data-testid={`media-img-${m.message_id}`} />
      </button>
    );
  }
  if (m.kind === "voice") {
    return <audio controls src={src} onError={onErr} className="max-w-[220px]" data-testid={`media-audio-${m.message_id}`} />;
  }
  if (m.kind === "video") {
    return <video controls src={src} onError={onErr} className="rounded-lg max-h-64" data-testid={`media-video-${m.message_id}`} />;
  }
  // PDF → in-app viewer; other files → direct download
  const pdf = isPdfMsg(m);
  return (
    <div className="flex items-center gap-2 text-sm">
      <button type="button" onClick={() => (pdf ? onOpen(m) : downloadChatMedia(m, t))} className="flex items-center gap-2 min-w-0" data-testid={`media-file-${m.message_id}`}>
        <span className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${pdf ? "bg-rose-100 text-rose-600" : "bg-slate-100 text-slate-600"}`}>
          {pdf ? <span className="text-[10px] font-black">PDF</span> : <FileIcon className="w-5 h-5" />}
        </span>
        <span className="underline truncate max-w-[160px] no-translate text-left">{m.file_name || "file"}</span>
      </button>
      <button type="button" onClick={() => downloadChatMedia(m, t)} className="p-1.5 rounded-full hover:bg-black/5 shrink-0" data-testid={`media-download-${m.message_id}`} aria-label="download">
        <Download className="w-4 h-4" />
      </button>
    </div>
  );
};

// ─── Main ──────────────────────────────────────────────────────────────────
export default function ChatRoomPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user, refresh } = useAuth();
  const { t, lang, setLang } = useI18n();
  const ptx = useContentTx();
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
  const [showLocation, setShowLocation] = useState(false);
  const [viewMedia, setViewMedia] = useState(null);
  const closeMedia = useCallback(() => setViewMedia(null), []);
  const [showEmoji, setShowEmoji] = useState(false);
  const [showGifts, setShowGifts] = useState(false);
  const [showLang, setShowLang] = useState(false);
  const [showBlockPopup, setShowBlockPopup] = useState(false);
  const [actionTarget, setActionTarget] = useState(null);   // message-action sheet (Reply / Delete)
  const longPressTimerRef = useRef(null);
  const longPressFired = useRef(false);
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
      onLocation: (u) => {
        setMsgs((prev) => prev.map((x) => {
          if (x.message_id !== u.message_id || !x.location) return x;
          if (u.expired) return { ...x, location: null, location_expired: true };
          return { ...x, location: { ...x.location, lat: u.lat, lng: u.lng, updated_at: u.updated_at } };
        }));
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

  // ─── Auto-translation (whole thread, incl. live messages) ────────────
  const { tx, isTranslated, isPending, busy: translating } = useChatTranslation(msgs, lang);
  const [showOrig, setShowOrig] = useState(() => new Set());
  const toggleOrig = (mid) => setShowOrig((p) => { const n = new Set(p); n.has(mid) ? n.delete(mid) : n.add(mid); return n; });

  // ─── Delete (single + bulk) & selection mode ─────────────────────────
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const [bulkConfirm, setBulkConfirm] = useState(null);
  const exitSelect = () => { setSelectMode(false); setSelected(new Set()); };
  const startSelect = (m) => { setSelectMode(true); setSelected(new Set([m.message_id])); };
  const toggleSelected = (mid) => setSelected((p) => { const n = new Set(p); n.has(mid) ? n.delete(mid) : n.add(mid); return n; });

  const deleteMessages = async (list, scope) => {
    setBulkConfirm(null);
    const ids = list.map((m) => m.message_id);
    try {
      if (ids.length === 1) await api.delete(`/messages/${ids[0]}?scope=${scope}`);
      else await api.post("/messages/delete-bulk", { message_ids: ids, scope });
      const idSet = new Set(ids);
      setMsgs((prev) => scope === "everyone"
        ? prev.map((x) => idSet.has(x.message_id) ? { ...x, deleted: true, text: "", media_url: null, file_name: null, gift_key: null, location: null } : x)
        : prev.filter((x) => !idSet.has(x.message_id)));
      exitSelect();
      toast.success(t("chat.deleted_toast"));
    } catch (e) {
      toast.error(e.response?.data?.detail || t("common.error"));
    }
  };

  const startLongPress = (m) => {
    clearTimeout(longPressTimerRef.current);
    if (selectMode) return;
    longPressTimerRef.current = setTimeout(() => {
      longPressFired.current = true;
      setActionTarget(m); navigator.vibrate?.(15);
    }, 550);
  };
  const cancelLongPress = () => { clearTimeout(longPressTimerRef.current); };

  // ─── Swipe-right to reply ─────────────────────────────────────────────
  const onMsgTouchStart = (m) => (e) => {
    longPressFired.current = false;
    startLongPress(m);
    if (m.deleted || selectMode) return;
    const t0 = e.touches[0];
    swipeRef.current = { startX: t0.clientX, startY: t0.clientY, id: m.message_id, active: true, locked: null };
  };
  const onMsgTouchMove = (m) => (e) => {
    const s = swipeRef.current;
    if (!s.active || s.id !== m.message_id) return;
    const t0 = e.touches[0];
    const dx = t0.clientX - s.startX;
    const dy = t0.clientY - s.startY;
    if (Math.abs(dx) > 8 || Math.abs(dy) > 8) cancelLongPress();
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

  // ─── Location share (map pin picker) ─────────────────────────────────
  const LOCATION_COST = 2;
  const [locBusy, setLocBusy] = useState(false);
  const noCoinsForLocation = () => {
    setShowLocation(false);
    toast.error(t("chat.loc_no_coins"), { duration: 5000 });
    nav("/premium");
  };
  const shareLocation = () => {
    setShowTray(false);
    if ((status.coins || 0) < LOCATION_COST) return noCoinsForLocation();
    setShowLocation(true);
  };
  const sendLocation = async ({ lat, lng, place, live }) => {
    setLocBusy(true);
    try {
      const { data } = await api.post(`/chats/${id}/send`, { kind: "location", lat, lng, place, live, reply_to: reply?.message_id });
      setMsgs((prev) => prev.some((x) => x.message_id === data.message_id) ? prev : [...prev, data]);
      setShowLocation(false); setReply(null);
      if (live) startLiveShare(data.message_id, data.location_expires_at);
      toast.success(t("chat.loc_sent").replace("{n}", LOCATION_COST));
      refreshStatus(); refresh(); scrollBottom();
    } catch (e) {
      if (e.response?.status === 402) { refreshStatus(); return noCoinsForLocation(); }
      const d = e.response?.data?.detail;
      toast.error(typeof d === "string" ? d : d?.message || t("common.error"));
    } finally { setLocBusy(false); }
  };
  const onLocationExpired = useCallback((mid) => {
    setMsgs((prev) => prev.map((x) => x.message_id === mid && x.location ? { ...x, location: null, location_expired: true } : x));
  }, []);

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
          {selectMode && <SelectionBar count={selected.size} t={t} onCancel={exitSelect}
            onDelete={() => setBulkConfirm(msgs.filter((x) => selected.has(x.message_id)))} />}
          <button data-testid="chat-back" onClick={() => nav(-1)} className="p-2 -ml-2 rounded-full hover:bg-slate-100"><ArrowLeft className="w-5 h-5 text-slate-700" /></button>
          {other && (
            <>
              <div className="relative">
                {other.photos?.[0]
                  ? <img src={other.photos[0]} alt="" className="w-10 h-10 rounded-full object-cover" data-testid="chat-header-avatar" />
                  : <div data-testid="chat-header-avatar" className="w-10 h-10 rounded-full bg-rose-100 text-rose-600 font-bold flex items-center justify-center no-translate">{(other.name || "?")[0]}</div>}
                {other.online && <span className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-emerald-500 border-2 border-white" />}
              </div>
              <div className="flex-1 min-w-0" onClick={() => nav(`/profile/${other.user_id}`)}>
                <p className="font-semibold text-slate-900 truncate no-translate">{ptx(other.name, "name")}, {other.age}</p>
                <p className="text-[11px] text-emerald-600">
                  {typingPeer ? t("chat.typing") : (other.online ? t("chat.online") : t("chat.recent"))}
                </p>
              </div>
              <div data-testid="chat-coins-header" className="flex items-center gap-1 text-xs text-slate-600 bg-slate-100 px-2 py-1 rounded-full">
                <span>💰</span><span className="font-semibold">{status.coins}</span>
              </div>
            </>
          )}
          {translating && (
            <span data-testid="chat-translating" className="absolute left-1/2 -translate-x-1/2 -bottom-3 z-10 text-[10px] px-2 py-0.5 rounded-full bg-sky-100 text-sky-700 flex items-center gap-1 shadow-sm">
              <Globe className="w-3 h-3 animate-spin" /> {t("chat.translating")}
            </span>
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
            const isSel = selected.has(m.message_id);
            const swiping = swipeState.id === m.message_id;
            const dx = swiping ? swipeState.dx : 0;
            const showHint = swiping && dx > 8;
            const highlighted = highlightId === m.message_id;
            const repliedSenderName = replied
              ? (replied.from_user === user?.user_id ? t("chat.you") : ptx(other?.name || "", "name"))
              : "";
            const repliedSnippet = replied
              ? (tx(replied.text) || {
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
                className={`chat-msg-row flex relative items-center gap-2 ${mine ? "justify-end" : "justify-start"} ${highlighted ? "chat-msg-flash" : ""} ${selectMode ? "cursor-pointer -mx-3 px-3 py-0.5" : ""} ${isSel ? "bg-sky-100/70" : ""}`}
                style={{ transform: dx ? `translateX(${dx}px)` : undefined }}
                onTouchStart={onMsgTouchStart(m)}
                onTouchMove={onMsgTouchMove(m)}
                onTouchEnd={(e) => { cancelLongPress(); if (longPressFired.current && e.cancelable) e.preventDefault(); onMsgTouchEnd(m)(e); }}
                onTouchCancel={(e) => { cancelLongPress(); onMsgTouchEnd(m)(e); }}
                onMouseDown={() => { longPressFired.current = false; startLongPress(m); }}
                onMouseUp={cancelLongPress}
                onMouseLeave={cancelLongPress}
                onContextMenu={(e) => { e.preventDefault(); if (!selectMode) setActionTarget(m); }}
                onClickCapture={(e) => {
                  if (selectMode) { e.preventDefault(); e.stopPropagation(); toggleSelected(m.message_id); }
                  else if (longPressFired.current) { e.preventDefault(); e.stopPropagation(); longPressFired.current = false; }
                }}
              >
                {selectMode && (
                  <span data-testid={`select-check-${m.message_id}`} className={`order-first w-5 h-5 shrink-0 rounded-full border-2 flex items-center justify-center ${isSel ? "bg-sky-500 border-sky-500 text-white" : "border-slate-300 bg-white"} ${mine ? "mr-auto" : ""}`}>
                    {isSel && <Check className="w-3 h-3" />}
                  </span>
                )}
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
                      ) : m.kind === "location" && !locked ? (
                        <LocationBubble m={m} mine={mine} onExpire={onLocationExpired} />
                      ) : ["image", "voice", "video", "file"].includes(m.kind) && m.media_url ? (
                        <MediaBubble m={m} onOpen={setViewMedia} t={t} />
                      ) : (
                        <p data-testid={`msg-text-${m.message_id}`} className={`whitespace-pre-wrap break-words text-[15px] leading-snug no-translate transition-opacity ${isPending(m.text) ? "opacity-50 animate-pulse" : ""}`}>
                          {showOrig.has(m.message_id) ? m.text : tx(m.text)}
                        </p>
                      )}
                      {isTranslated(m.text) && (
                        <button data-testid={`toggle-orig-${m.message_id}`} onClick={() => toggleOrig(m.message_id)} className="mt-0.5 text-[10px] text-sky-600 flex items-center gap-1">
                          <Globe className="w-3 h-3" /> {showOrig.has(m.message_id) ? t("chat.show_translation") : t("chat.show_original")}
                        </button>
                      )}
                      <div className="flex items-center justify-end gap-1 mt-0.5 text-[10px] text-slate-500">
                        <span>{fmtTime(m.created_at)}</span>
                        {mine && (m.read ? <CheckCheck className="w-3.5 h-3.5 text-sky-500" /> : <Check className="w-3.5 h-3.5" />)}
                      </div>
                    </div>
                  )}
                  {!locked && !m.deleted && (
                    <div className={`flex gap-2 mt-0.5 text-[10px] text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity ${mine ? "justify-end" : ""}`}>
                      <button onClick={() => setReply(m)} data-testid={`reply-${m.message_id}`}>{t("chat.reply")}</button>
                      {mine && <button onClick={() => setActionTarget(m)} data-testid={`delete-${m.message_id}`}>{t("chat.delete_me")}</button>}
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
          const senderName = replyMine ? t("chat.you") : ptx(other?.name || "", "name");
          const snippet = tx(reply.text) || {
            image: "🖼 " + t("chat.gift_gallery"),
            video: "🎬 " + t("chat.gift_camera"),
            voice: "🎤 " + t("chat.recording"),
            file: "📎 " + (reply.file_name || t("chat.gift_file")),
            gift: "🎁 " + t("chat.preview_gift"),
            location: "📍 " + t("chat.location"),
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
        <ChatMediaViewer m={viewMedia} onClose={closeMedia} />
        <LocationPicker open={showLocation} onClose={() => setShowLocation(false)} onSend={sendLocation} fallback={{ lat: user?.lat, lng: user?.lng }} coins={status.coins} cost={LOCATION_COST} busy={locBusy} />
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

        <MessageActionSheet m={actionTarget} uid={user?.user_id} t={t}
          copyValue={actionTarget ? (showOrig.has(actionTarget.message_id) ? actionTarget.text : tx(actionTarget.text)) : ""}
          onClose={() => setActionTarget(null)} onReply={setReply} onSelect={startSelect} onDelete={deleteMessages} />
        <BulkDeleteDialog msgs={bulkConfirm} uid={user?.user_id} t={t} onClose={() => setBulkConfirm(null)} onDelete={deleteMessages} />
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
