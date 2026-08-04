import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeContext";
import { Toaster } from "sonner";
import Landing from "@/pages/Landing";
import AuthCallback from "@/pages/AuthCallback";
import HomePage from "@/pages/HomePage";
import DiscoverPage from "@/pages/DiscoverPage";
import LikesPage from "@/pages/LikesPage";
import ChatsListPage from "@/pages/ChatsListPage";
import ChatRoomPage from "@/pages/ChatRoomPage";
import ProfilePage from "@/pages/ProfilePage";
import OtherProfilePage from "@/pages/OtherProfilePage";
import PremiumPage from "@/pages/PremiumPage";
import PurchaseHistoryPage from "@/pages/PurchaseHistoryPage";
import AdminNotifier from "@/components/lovreski/AdminNotifier";
import SettingsPage from "@/pages/SettingsPage";
import AdminPage from "@/pages/AdminPage";

const Protected = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted-foreground">Загрузка...</div>;
  if (!user) return <Navigate to="/" replace />;
  return children;
};

const AppRouter = () => {
  const location = useLocation();
  // Handle Emergent OAuth callback synchronously during render
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/home" element={<Protected><HomePage /></Protected>} />
      <Route path="/discover" element={<Protected><DiscoverPage /></Protected>} />
      <Route path="/likes" element={<Protected><LikesPage /></Protected>} />
      <Route path="/chats" element={<Protected><ChatsListPage /></Protected>} />
      <Route path="/chats/:id" element={<Protected><ChatRoomPage /></Protected>} />
      <Route path="/profile" element={<Protected><ProfilePage /></Protected>} />
      <Route path="/profile/:id" element={<Protected><OtherProfilePage /></Protected>} />
      <Route path="/premium" element={<Protected><PremiumPage /></Protected>} />
      <Route path="/purchase-history" element={<Protected><PurchaseHistoryPage /></Protected>} />
      <Route path="/settings" element={<Protected><SettingsPage /></Protected>} />
      <Route path="/settings/discovery" element={<Protected><SettingsPage /></Protected>} />
      <Route path="/admin" element={<Protected><AdminPage /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <AppRouter />
          <AdminNotifier />
          <Toaster position="top-center" richColors />
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
