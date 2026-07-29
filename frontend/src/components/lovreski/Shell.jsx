import { Link, NavLink } from "react-router-dom";
import { Home, Compass, Heart, MessageCircle, User } from "lucide-react";

const tabs = [
  { to: "/home", label: "Главная", icon: Home, testid: "nav-home" },
  { to: "/discover", label: "Поиск", icon: Compass, testid: "nav-discover" },
  { to: "/likes", label: "Лайки", icon: Heart, testid: "nav-likes" },
  { to: "/chats", label: "Чаты", icon: MessageCircle, testid: "nav-chats" },
  { to: "/profile", label: "Профиль", icon: User, testid: "nav-profile" },
];

export const BottomNav = () => (
  <nav
    data-testid="bottom-nav"
    className="fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-md z-50 border-t border-border bg-background/85 backdrop-blur-xl"
  >
    <ul className="flex justify-around items-center h-16 px-2">
      {tabs.map(({ to, label, icon: Icon, testid }) => (
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
            <span className="text-[10px] font-semibold uppercase tracking-wider">{label}</span>
          </NavLink>
        </li>
      ))}
    </ul>
  </nav>
);

export const MobileShell = ({ children, hideNav }) => (
  <div className="min-h-screen bg-background flex justify-center">
    <div className="w-full max-w-md relative bg-background pb-20 shadow-xl border-x border-border/60 min-h-screen">
      {children}
      {!hideNav && <BottomNav />}
    </div>
  </div>
);
