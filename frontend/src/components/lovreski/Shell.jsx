import { Link, NavLink } from "react-router-dom";
import { Home, Compass, Heart, MessageCircle, User } from "lucide-react";
import { useI18n } from "@/lib/i18n";

const TABS = [
  { to: "/home", key: "nav.home", icon: Home, testid: "nav-home" },
  { to: "/discover", key: "nav.search", icon: Compass, testid: "nav-discover" },
  { to: "/likes", key: "nav.likes", icon: Heart, testid: "nav-likes" },
  { to: "/chats", key: "nav.chats", icon: MessageCircle, testid: "nav-chats" },
  { to: "/profile", key: "nav.profile", icon: User, testid: "nav-profile" },
];

export const BottomNav = () => {
  const { t } = useI18n();
  return (
    <nav
      data-testid="bottom-nav"
      className="fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-md z-50 border-t border-border bg-background/85 backdrop-blur-xl"
    >
      <ul className="flex justify-around items-center h-16 px-2">
        {TABS.map(({ to, key, icon: Icon, testid }) => (
          <li key={to} className="flex-1">
            <NavLink
              to={to}
              data-testid={testid}
              className={({ isActive }) =>
                `flex flex-col items-center justify-center gap-1 h-16 transition-colors duration-200 ${
                  isActive ? "text-primary" : "text-muted-foreground"
                }`
              }
            >
              <Icon className="w-6 h-6" strokeWidth={2.2} />
              <span className="text-[10px] font-semibold uppercase tracking-wider">{t(key)}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
};

export const MobileShell = ({ children, hideNav }) => (
  <div className="min-h-screen bg-background flex justify-center">
    <div className="w-full max-w-md relative bg-background pb-20 shadow-xl border-x border-border/60 min-h-screen">
      {children}
      {!hideNav && <BottomNav />}
    </div>
  </div>
);
