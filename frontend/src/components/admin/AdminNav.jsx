import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  LayoutDashboard, ReceiptText, Undo2, Flag, MoreHorizontal, CreditCard, Users, FileText, BellRing, Settings, X,
} from "lucide-react";

export const ADMIN_TABS = [
  { k: "dashboard", l: "Дашборд", short: "Главная", icon: LayoutDashboard, main: true },
  { k: "support", l: "Verification", short: "Чеки", icon: ReceiptText, main: true },
  { k: "refunds", l: "Refund Requests", short: "Возвраты", icon: Undo2, main: true },
  { k: "reports", l: "Жалобы", short: "Жалобы", icon: Flag, main: true },
  { k: "payments", l: "Платежи", icon: CreditCard },
  { k: "users", l: "Пользователи", icon: Users },
  { k: "legal", l: "Правовые", icon: FileText },
  { k: "push", l: "Push", icon: BellRing },
  { k: "settings", l: "Настройки", icon: Settings },
];

const Badge = ({ n, testid, className = "" }) =>
  n > 0 ? (
    <span data-testid={testid} className={`min-w-[18px] h-[18px] px-1 rounded-full bg-rose-500 text-white text-[10px] font-bold flex items-center justify-center ${className}`}>
      {n > 99 ? "99+" : n}
    </span>
  ) : null;

const DesktopTabs = ({ tab, setTab, badges }) => (
  <div className="hidden md:flex gap-1 mb-6 bg-muted p-1 rounded-full w-fit max-w-full overflow-x-auto whitespace-nowrap">
    {ADMIN_TABS.map((t) => (
      <button key={t.k} data-testid={`admin-tab-${t.k}`} onClick={() => setTab(t.k)}
        className={`relative px-4 py-2 rounded-full font-semibold text-sm transition-colors ${tab === t.k ? "bg-card shadow" : "text-muted-foreground hover:text-foreground"}`}>
        {t.l}
        <Badge n={badges[t.k]} testid={`badge-${t.k}`} className="absolute -top-1 -right-1" />
      </button>
    ))}
  </div>
);

const MoreSheet = ({ open, onClose, tab, setTab, badges }) => (
  <AnimatePresence>
    {open && (
      <motion.div className="md:hidden fixed inset-0 z-[80] bg-black/50 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
        <motion.div data-testid="admin-more-sheet" onClick={(e) => e.stopPropagation()}
          initial={{ y: 80 }} animate={{ y: 0 }} exit={{ y: 80 }} transition={{ type: "spring", damping: 24 }}
          className="absolute bottom-0 inset-x-0 bg-card rounded-t-3xl border-t border-border p-4 pb-8">
          <div className="flex items-center justify-between mb-3 px-1">
            <p className="font-display font-bold">Ещё разделы</p>
            <button data-testid="admin-more-close" onClick={onClose} className="p-1.5 rounded-full hover:bg-muted"><X className="w-5 h-5" /></button>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {ADMIN_TABS.filter((t) => !t.main).map((t) => (
              <button key={t.k} data-testid={`admin-more-${t.k}`} onClick={() => { setTab(t.k); onClose(); }}
                className={`relative flex flex-col items-center gap-1.5 py-4 rounded-2xl text-xs font-semibold ${tab === t.k ? "bg-primary/10 text-primary" : "bg-muted text-foreground"}`}>
                <t.icon className="w-5 h-5" /> {t.l}
                <Badge n={badges[t.k]} className="absolute top-1.5 right-1.5" />
              </button>
            ))}
          </div>
        </motion.div>
      </motion.div>
    )}
  </AnimatePresence>
);

const BottomBar = ({ tab, setTab, badges, onMore }) => {
  const moreActive = !ADMIN_TABS.find((t) => t.k === tab)?.main;
  const moreBadge = ADMIN_TABS.filter((t) => !t.main).reduce((a, t) => a + (badges[t.k] || 0), 0);
  const Item = ({ active, onClick, icon: Icon, label, n, testid }) => (
    <button data-testid={testid} onClick={onClick} className={`relative flex-1 flex flex-col items-center gap-0.5 py-2 text-[10px] font-semibold transition-colors ${active ? "text-primary" : "text-muted-foreground"}`}>
      <span className="relative"><Icon className="w-5 h-5" /><Badge n={n} testid={`${testid}-badge`} className="absolute -top-2 -right-3" /></span>
      {label}
      {active && <span className="absolute top-0 h-0.5 w-8 rounded-full bg-primary" />}
    </button>
  );
  return (
    <nav data-testid="admin-bottom-nav" className="md:hidden fixed bottom-0 inset-x-0 z-[70] bg-card/95 backdrop-blur border-t border-border flex pb-[env(safe-area-inset-bottom)]">
      {ADMIN_TABS.filter((t) => t.main).map((t) => (
        <Item key={t.k} testid={`admin-mtab-${t.k}`} active={tab === t.k} onClick={() => setTab(t.k)} icon={t.icon} label={t.short} n={badges[t.k]} />
      ))}
      <Item testid="admin-mtab-more" active={moreActive} onClick={onMore} icon={MoreHorizontal} label="Ещё" n={moreBadge} />
    </nav>
  );
};

export const AdminNav = ({ tab, setTab, badges }) => {
  const [more, setMore] = useState(false);
  return (
    <>
      <DesktopTabs tab={tab} setTab={setTab} badges={badges} />
      <BottomBar tab={tab} setTab={setTab} badges={badges} onMore={() => setMore(true)} />
      <MoreSheet open={more} onClose={() => setMore(false)} tab={tab} setTab={setTab} badges={badges} />
    </>
  );
};
