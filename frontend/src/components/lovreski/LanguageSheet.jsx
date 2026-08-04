import { useState, useMemo } from "react";
import { X, Search, Check } from "lucide-react";
import { LANGUAGES, useI18n } from "@/lib/i18n";

const REGIONS = [
  { key: "global",   labelKey: "lang.region.global"   },
  { key: "europe",   labelKey: "lang.region.europe"   },
  { key: "asia",     labelKey: "lang.region.asia"     },
  { key: "americas", labelKey: "lang.region.americas" },
];

export default function LanguageSheet({ open, onClose, onSelect }) {
  const { lang, t } = useI18n();
  const [q, setQ] = useState("");
  const groups = useMemo(() => {
    const term = q.trim().toLowerCase();
    return REGIONS.map((r) => ({
      ...r,
      items: LANGUAGES[r.key].filter((l) =>
        !term || l.name.toLowerCase().includes(term) || l.code.toLowerCase().includes(term)
      ),
    })).filter((r) => r.items.length > 0);
  }, [q]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-end sm:items-center sm:justify-center" data-testid="lang-sheet">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative w-full sm:max-w-md bg-background rounded-t-3xl sm:rounded-3xl flex flex-col" style={{ maxHeight: "85vh" }}>
        <div className="flex items-center justify-between px-4 pt-4 pb-2">
          <h3 className="font-display font-bold text-lg">{t("lang.title")}</h3>
          <button data-testid="lang-close" onClick={onClose} className="p-2 rounded-full hover:bg-muted"><X className="w-5 h-5" /></button>
        </div>
        <div className="px-4 pb-2">
          <div className="flex items-center gap-2 bg-muted rounded-full px-3 py-2">
            <Search className="w-4 h-4 text-muted-foreground" />
            <input
              data-testid="lang-search"
              value={q} onChange={(e) => setQ(e.target.value)}
              placeholder={t("lang.search")}
              className="flex-1 bg-transparent outline-none text-sm"
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-4">
          {groups.map((g) => (
            <div key={g.key} className="mb-2">
              <p className="px-3 pt-3 pb-1 text-[11px] uppercase tracking-widest text-muted-foreground font-semibold">{t(g.labelKey)}</p>
              {g.items.map((l) => {
                const selected = l.code === lang;
                return (
                  <button
                    key={l.code}
                    data-testid={`lang-${l.code}`}
                    onClick={() => { onSelect?.(l); }}
                    className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-left ${selected ? "bg-primary/10" : "hover:bg-muted"}`}
                  >
                    <span className="text-2xl">{l.flag}</span>
                    <span className="flex-1 text-sm">{l.name}</span>
                    <span className="text-[10px] text-muted-foreground">{l.code}</span>
                    {selected && <Check className="w-4 h-4 text-primary" />}
                  </button>
                );
              })}
            </div>
          ))}
          {groups.length === 0 && <p className="text-center text-sm text-muted-foreground py-8">—</p>}
        </div>
      </div>
    </div>
  );
}
