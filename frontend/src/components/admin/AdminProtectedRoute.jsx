import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Shield } from "lucide-react";
import { verifyAdminToken } from "@/lib/adminApi";

export const AdminCheckingScreen = () => (
  <div data-testid="admin-checking" className="min-h-screen flex flex-col items-center justify-center gap-3 bg-background text-muted-foreground">
    <Shield className="w-8 h-8 text-primary animate-pulse" />
    <p className="text-sm">Проверка доступа...</p>
  </div>
);

// Silently verifies the stored admin token before rendering admin pages.
export const AdminProtectedRoute = ({ children }) => {
  const [state, setState] = useState("checking");
  const loc = useLocation();
  useEffect(() => {
    let alive = true;
    verifyAdminToken().then((ok) => alive && setState(ok ? "ok" : "denied"));
    return () => { alive = false; };
  }, []);
  if (state === "checking") return <AdminCheckingScreen />;
  if (state === "denied") return <Navigate to="/admin/login" replace state={{ from: loc.pathname }} />;
  return children;
};
