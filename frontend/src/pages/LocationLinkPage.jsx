import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { MapPin, Clock, Loader2, Navigation } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { getCurrentPosition, distanceKm, fmtDistance, googleMapsUrl } from "@/lib/liveLocation";

// Public landing for a shared location link (server enforces the 5-minute expiry).
export default function LocationLinkPage() {
  const { token } = useParams();
  const { t: rawT } = useI18n();
  const FALLBACK = { "chat.loc_link_expired": "Срок действия ссылки на локацию истёк", "chat.loc_link_missing": "Ссылка не найдена",
    "chat.loc_distance": "Расстояние до вас: {d}", "chat.location_open": "Открыть в Google Картах" };
  const t = (k) => { const v = rawT(k); return v === k ? FALLBACK[k] || k : v; };
  const [st, setSt] = useState({ loading: true });

  useEffect(() => {
    api.get(`/loc/${token}`)
      .then(async ({ data }) => {
        let here = null;
        try { here = await getCurrentPosition(8000); } catch { /* optional */ }
        const url = googleMapsUrl(data.lat, data.lng, here);
        setSt({ loading: false, data, url, dist: here ? distanceKm(here, [data.lat, data.lng]) : null });
        window.location.href = url;
      })
      .catch((e) => setSt({ loading: false, expired: e.response?.status === 410, error: true }));
  }, [token]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-6">
      <div data-testid="loc-link-page" className="w-full max-w-sm text-center p-8 rounded-3xl bg-card border border-border">
        {st.loading ? (
          <Loader2 className="w-8 h-8 animate-spin mx-auto text-primary" />
        ) : st.error ? (
          <>
            <Clock className="w-10 h-10 mx-auto text-amber-500" />
            <p data-testid="loc-link-expired" className="mt-3 font-display font-bold">{st.expired ? t("chat.loc_link_expired") : t("chat.loc_link_missing")}</p>
          </>
        ) : (
          <>
            <MapPin className="w-10 h-10 mx-auto text-rose-500" />
            {st.data.place && <p className="mt-2 font-semibold no-translate">{st.data.place}</p>}
            {st.dist != null && <p data-testid="loc-link-distance" className="mt-1 text-sm text-muted-foreground">{t("chat.loc_distance").replace("{d}", fmtDistance(st.dist))}</p>}
            <a data-testid="loc-link-open" href={st.url} className="mt-5 inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-primary text-primary-foreground font-semibold text-sm">
              <Navigation className="w-4 h-4" /> {t("chat.location_open")}
            </a>
          </>
        )}
        <Link to="/" className="block mt-6 text-xs text-muted-foreground">Lovreski</Link>
      </div>
    </div>
  );
}
