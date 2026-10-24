import { useEffect, useState } from "react";
import { MapContainer, TileLayer, Marker, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { MapPin, LocateFixed, ShieldCheck, Clock, ExternalLink } from "lucide-react";
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

export const mapsUrl = (lat, lng) => `https://yandex.ru/maps/?pt=${lng},${lat}&z=16&l=map`;

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

export const LocationPicker = ({ open, onClose, onSend, fallback }) => {
  const { t } = useI18n();
  const [pos, setPos] = useState(null);
  const [place, setPlace] = useState("");
  const [locating, setLocating] = useState(false);

  const locate = () => {
    if (!navigator.geolocation) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (p) => { setPos([p.coords.latitude, p.coords.longitude]); setLocating(false); },
      () => setLocating(false),
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  useEffect(() => {
    if (!open) return;
    setPlace("");
    setPos(fallback?.lat != null && fallback?.lng != null ? [fallback.lat, fallback.lng] : DEFAULT_CENTER);
    locate();
    // eslint-disable-next-line
  }, [open]);

  return (
    <BottomSheet open={open} onClose={onClose} title={t("chat.location_title")} testId="location-picker">
      <p className="text-xs text-muted-foreground mb-2">{t("chat.location_hint")}</p>
      <div className="relative h-64 rounded-2xl overflow-hidden border border-border" data-testid="location-map">
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
      <input data-testid="location-place-input" value={place} maxLength={120} onChange={(e) => setPlace(e.target.value)} placeholder={t("chat.location_place_ph")}
        className="mt-3 w-full px-3 py-2 rounded-xl bg-muted border border-border text-sm" />
      <div className="mt-3"><SafetyNote /></div>
      <p className="mt-2 text-[11px] text-muted-foreground flex items-center gap-1"><Clock className="w-3 h-3" /> {t("chat.location_expires")}</p>
      <button data-testid="location-send-btn" disabled={!pos} onClick={() => onSend({ lat: pos[0], lng: pos[1], place: place.trim() })}
        className="mt-4 w-full py-3 rounded-full bg-primary text-primary-foreground font-semibold flex items-center justify-center gap-2 disabled:opacity-60">
        <MapPin className="w-4 h-4" /> {t("chat.location_send")}
      </button>
    </BottomSheet>
  );
};

export const LocationBubble = ({ m, place }) => {
  const { t } = useI18n();
  const loc = m.location;
  if (!loc) {
    return (
      <div data-testid={`location-expired-${m.message_id}`} className="flex items-center gap-2 text-sm text-slate-500 italic py-1">
        <MapPin className="w-4 h-4" /> {t("chat.location_expired")}
      </div>
    );
  }
  const pos = [loc.lat, loc.lng];
  return (
    <div className="w-56" data-testid={`location-bubble-${m.message_id}`}>
      <a href={mapsUrl(loc.lat, loc.lng)} target="_blank" rel="noreferrer" className="block h-32 rounded-lg overflow-hidden relative">
        <MapContainer center={pos} zoom={15} className="h-full w-full pointer-events-none" zoomControl={false} dragging={false}
          scrollWheelZoom={false} doubleClickZoom={false} touchZoom={false} keyboard={false} attributionControl={false}>
          <TileLayer url={TILE} />
          <Marker position={pos} icon={pinIcon} />
        </MapContainer>
      </a>
      {loc.place && <p className="mt-1 text-sm font-semibold no-translate">{place || loc.place}</p>}
      <a data-testid={`location-open-${m.message_id}`} href={mapsUrl(loc.lat, loc.lng)} target="_blank" rel="noreferrer" className="mt-1 text-xs text-sky-600 flex items-center gap-1">
        <ExternalLink className="w-3 h-3" /> {t("chat.location_open")}
      </a>
      <div className="mt-1.5"><SafetyNote compact /></div>
    </div>
  );
};
