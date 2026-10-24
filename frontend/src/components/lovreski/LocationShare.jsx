import { useEffect, useState } from "react";
import { MapContainer, TileLayer, Marker, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { MapPin, LocateFixed, ShieldCheck, Clock, ExternalLink, Radio, Link as LinkIcon } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { copyText } from "@/components/lovreski/MessageActions";
import { subscribeLive, isLiveActive, stopLiveShare, getCurrentPosition, distanceKm, fmtDistance, googleMapsUrl } from "@/lib/liveLocation";
import { BottomSheet } from "@/components/lovreski/BottomSheet";
import { useI18n } from "@/lib/i18n";

const TILE = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTR = "&copy; OpenStreetMap";
const DEFAULT_CENTER = [55.7558, 37.6173];

export const pinIcon = L.divIcon({
  className: "",
  html: '<div style="width:34px;height:34px;transform:translate(-50%,-100%);position:absolute"><svg viewBox="0 0 24 24" width="34" height="34" fill="#f43f5e" stroke="#fff" stroke-width="1.5"><path d="M12 22s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="10" r="2.6" fill="#fff"/></svg></div>',
  iconSize: [0, 0],
});


const Recenter = ({ pos }) => {
  const map = useMap();
  useEffect(() => { map.setView(pos, map.getZoom()); }, [pos, map]);
  return null;
};

const ClickToMove = ({ onPick }) => {
  useMapEvents({ click: (e) => onPick([e.latlng.lat, e.latlng.lng]) });
  return null;
};

export const SafetyNote = ({ compact }) => {
  const { t } = useI18n();
  return (
    <div data-testid="location-safety-note" className={`flex gap-2 rounded-xl bg-amber-50 text-amber-800 border border-amber-200 ${compact ? "px-2 py-1 text-[10px]" : "px-3 py-2 text-xs"}`}>
      <ShieldCheck className={`${compact ? "w-3 h-3" : "w-4 h-4"} shrink-0 mt-0.5`} />
      <span>{t("chat.location_safety")}</span>
    </div>
  );
};

export const LocationPicker = ({ open, onClose, onSend, fallback, coins = 0, cost = 2, busy = false }) => {
  const { t } = useI18n();
  const [pos, setPos] = useState(null);
  const [place, setPlace] = useState("");
  const [locating, setLocating] = useState(false);
  const [geoErr, setGeoErr] = useState("");
  const enough = coins >= cost;

  const locate = () => new Promise((resolve) => {
    if (!navigator.geolocation) { setGeoErr(t("chat.loc_geo_unsupported")); return resolve(null); }
    setLocating(true); setGeoErr("");
    navigator.geolocation.getCurrentPosition(
      (p) => { const v = [p.coords.latitude, p.coords.longitude]; setPos(v); setLocating(false); resolve(v); },
      () => { setLocating(false); setGeoErr(t("chat.loc_geo_denied")); resolve(null); },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  });

  useEffect(() => {
    if (!open) return;
    setPlace(""); setGeoErr("");
    setPos(fallback?.lat != null && fallback?.lng != null ? [fallback.lat, fallback.lng] : DEFAULT_CENTER);
    locate();
    // eslint-disable-next-line
  }, [open]);

  const shareLive = async () => {
    const here = await locate();
    if (here) onSend({ lat: here[0], lng: here[1], place: place.trim(), live: true });
  };

  return (
    <BottomSheet open={open} onClose={onClose} title={t("chat.location_title")} testId="location-picker">
      <div data-testid="location-cost" className={`mb-3 flex items-center justify-between rounded-xl px-3 py-2 text-xs font-semibold ${enough ? "bg-amber-50 text-amber-800" : "bg-red-50 text-red-700"}`}>
        <span>{t("chat.loc_cost").replace("{n}", cost)}</span>
        <span data-testid="location-balance">💰 {coins}</span>
      </div>
      <button data-testid="location-share-live" disabled={busy || locating} onClick={shareLive}
        className="w-full mb-3 py-3 rounded-2xl bg-emerald-500 text-white font-semibold flex items-center justify-center gap-2 disabled:opacity-60">
        <Radio className="w-4 h-4" /> {t("chat.loc_share_live")}
      </button>
      <p className="text-xs text-muted-foreground mb-2">{t("chat.location_hint")}</p>
      <div className="relative h-56 rounded-2xl overflow-hidden border border-border isolate" data-testid="location-map">
        {pos && (
          <MapContainer center={pos} zoom={15} className="h-full w-full" attributionControl={false}>
            <TileLayer url={TILE} attribution={ATTR} />
            <Recenter pos={pos} />
            <ClickToMove onPick={setPos} />
            <Marker position={pos} icon={pinIcon} draggable eventHandlers={{ dragend: (e) => { const ll = e.target.getLatLng(); setPos([ll.lat, ll.lng]); } }} />
          </MapContainer>
        )}
        <button data-testid="location-locate-me" onClick={locate} className="absolute z-[500] right-2 bottom-2 px-3 py-1.5 rounded-full bg-white shadow text-xs font-semibold text-slate-800 flex items-center gap-1">
          <LocateFixed className={`w-3.5 h-3.5 ${locating ? "animate-spin" : ""}`} /> {t("chat.location_mine")}
        </button>
      </div>
      {geoErr && <p data-testid="location-geo-error" className="mt-2 text-[11px] text-red-600">{geoErr}</p>}
      <input data-testid="location-place-input" value={place} maxLength={120} onChange={(e) => setPlace(e.target.value)} placeholder={t("chat.location_place_ph")}
        className="mt-3 w-full px-3 py-2 rounded-xl bg-muted border border-border text-sm" />
      <div className="mt-3"><SafetyNote /></div>
      <p className="mt-2 text-[11px] text-muted-foreground flex items-center gap-1"><Clock className="w-3 h-3" /> {t("chat.location_expires")}</p>
      <button data-testid="location-send-btn" disabled={!pos || busy} onClick={() => onSend({ lat: pos[0], lng: pos[1], place: place.trim(), live: false })}
        className="mt-4 w-full py-3 rounded-full bg-primary text-primary-foreground font-semibold flex items-center justify-center gap-2 disabled:opacity-60">
        <MapPin className="w-4 h-4" /> {t("chat.location_send")}
      </button>
    </BottomSheet>
  );
};

const useCountdown = (iso) => {
  const [left, setLeft] = useState(() => Math.max(0, new Date(iso).getTime() - Date.now()));
  useEffect(() => {
    if (!iso) return;
    const tick = () => setLeft(Math.max(0, new Date(iso).getTime() - Date.now()));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [iso]);
  return left;
};

const fmtLeft = (ms) => { const s = Math.ceil(ms / 1000); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };

// Opens the server-validated link: expired → message; valid → Google Maps + distance.
export async function openLocationLink(token, t) {
  const win = window.open("", "_blank"); // opened synchronously so popup blockers allow it
  try {
    const { data } = await api.get(`/loc/${token}`);
    let here = null;
    try { here = await getCurrentPosition(8000); } catch { /* distance optional */ }
    if (here) toast.success(t("chat.loc_distance").replace("{d}", fmtDistance(distanceKm(here, [data.lat, data.lng]))), { duration: 6000 });
    const url = googleMapsUrl(data.lat, data.lng, here);
    if (win) win.location.href = url; else window.location.href = url;
    return { ...data, distance: here ? distanceKm(here, [data.lat, data.lng]) : null };
  } catch (e) {
    if (win) win.close();
    toast.error(e.response?.status === 410 ? t("chat.loc_link_expired") : t("common.error"));
    return null;
  }
}

export const LocationBubble = ({ m, place, mine, onExpire }) => {
  const { t } = useI18n();
  const loc = m.location;
  const left = useCountdown(m.location_expires_at);
  const [, force] = useState(0);
  const [dist, setDist] = useState(null);
  useEffect(() => subscribeLive(() => force((x) => x + 1)), []);
  useEffect(() => { if (loc && left === 0 && m.location_expires_at) onExpire?.(m.message_id); }, [left, loc, m.location_expires_at, m.message_id, onExpire]);

  if (!loc || left === 0) {
    return (
      <div data-testid={`location-expired-${m.message_id}`} className="flex items-center gap-2 text-sm text-slate-500 italic py-1">
        <MapPin className="w-4 h-4" /> {t("chat.loc_link_expired")}
      </div>
    );
  }
  const pos = [loc.lat, loc.lng];
  const open = async () => { const r = await openLocationLink(loc.token, t); if (r?.distance != null) setDist(r.distance); };
  const copy = () => copyText(`${window.location.origin}/l/${loc.token}`, t);
  const liveActive = mine && loc.live && isLiveActive(m.message_id);
  return (
    <div className="w-56" data-testid={`location-bubble-${m.message_id}`}>
      <button type="button" onClick={open} className="block w-full h-32 rounded-lg overflow-hidden relative isolate" data-testid={`location-map-${m.message_id}`}>
        <MapContainer center={pos} zoom={15} className="h-full w-full pointer-events-none" zoomControl={false} dragging={false}
          scrollWheelZoom={false} doubleClickZoom={false} touchZoom={false} keyboard={false} attributionControl={false}>
          <TileLayer url={TILE} />
          <Recenter pos={pos} />
          <Marker position={pos} icon={pinIcon} />
        </MapContainer>
        {loc.live && <span className="absolute top-1.5 left-1.5 z-[500] px-2 py-0.5 rounded-full bg-emerald-500 text-white text-[10px] font-bold flex items-center gap-1"><Radio className="w-3 h-3 animate-pulse" /> LIVE</span>}
        <span data-testid={`location-countdown-${m.message_id}`} className="absolute top-1.5 right-1.5 z-[500] px-2 py-0.5 rounded-full bg-black/60 text-white text-[10px] font-bold">{fmtLeft(left)}</span>
      </button>
      {loc.place && <p className="mt-1 text-sm font-semibold no-translate">{place || loc.place}</p>}
      {dist != null && <p data-testid={`location-distance-${m.message_id}`} className="text-xs text-slate-600 mt-0.5">{t("chat.loc_distance").replace("{d}", fmtDistance(dist))}</p>}
      <div className="mt-1 flex items-center gap-3">
        <button type="button" data-testid={`location-open-${m.message_id}`} onClick={open} className="text-xs text-sky-600 flex items-center gap-1">
          <ExternalLink className="w-3 h-3" /> {t("chat.location_open")}
        </button>
        <button type="button" data-testid={`location-copy-link-${m.message_id}`} onClick={copy} className="text-xs text-slate-500 flex items-center gap-1">
          <LinkIcon className="w-3 h-3" /> {t("chat.loc_copy_link")}
        </button>
      </div>
      {liveActive && (
        <button type="button" data-testid={`location-stop-live-${m.message_id}`} onClick={() => stopLiveShare(m.message_id)} className="mt-1.5 w-full py-1.5 rounded-full bg-red-50 text-red-600 text-xs font-semibold">
          {t("chat.loc_stop_live")}
        </button>
      )}
      <div className="mt-1.5"><SafetyNote compact /></div>
    </div>
  );
};
