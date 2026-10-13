// Full-screen match celebration overlay — shown when both users like each other.
import { motion } from "framer-motion";
import { Heart, MessageCircle, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

export const MatchCelebration = ({ matchUser, onClose }) => {
  const { user } = useAuth();
  const nav = useNavigate();
  if (!matchUser) return null;

  const myPhoto = user?.photos?.[0];
  const theirPhoto = matchUser?.photos?.[0];

  return (
    <motion.div
      data-testid="match-celebration"
      className="fixed inset-0 z-[95] flex flex-col items-center justify-center px-6"
      style={{ background: "radial-gradient(ellipse at 50% 30%, rgba(217,22,86,0.35), rgba(10,8,12,0.97) 70%)" }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <button
        data-testid="match-close"
        onClick={onClose}
        aria-label="Закрыть"
        className="absolute top-5 right-5 p-2 rounded-full bg-white/10 text-white/80 hover:bg-white/20"
      >
        <X className="w-5 h-5" />
      </button>

      <motion.p
        className="text-primary font-display font-semibold tracking-[0.3em] text-xs mb-2"
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.1 }}
      >
        ЭТО МЭТЧ!
      </motion.p>
      <motion.h2
        className="font-display font-black text-white text-4xl text-center leading-tight"
        initial={{ scale: 0.6, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 260, damping: 18, delay: 0.15 }}
      >
        Взаимная симпатия
      </motion.h2>

      {/* Overlapping photos with pulsing heart */}
      <div className="relative flex items-center justify-center mt-10 mb-4">
        <motion.div
          initial={{ x: -80, opacity: 0, rotate: -10 }}
          animate={{ x: -22, opacity: 1, rotate: -6 }}
          transition={{ type: "spring", stiffness: 200, damping: 20, delay: 0.25 }}
          className="w-32 h-32 rounded-full border-4 border-white shadow-2xl overflow-hidden bg-white/10 z-10"
        >
          {myPhoto
            ? <img src={myPhoto} alt="Вы" className="w-full h-full object-cover" />
            : <div className="w-full h-full flex items-center justify-center text-4xl">🙂</div>}
        </motion.div>
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: [0, 1.4, 1] }}
          transition={{ delay: 0.5, duration: 0.5 }}
          className="z-20 -mx-2 w-14 h-14 rounded-full bg-primary flex items-center justify-center shadow-lg"
        >
          <Heart className="w-7 h-7 text-white" fill="currentColor" />
        </motion.div>
        <motion.div
          initial={{ x: 80, opacity: 0, rotate: 10 }}
          animate={{ x: 22, opacity: 1, rotate: 6 }}
          transition={{ type: "spring", stiffness: 200, damping: 20, delay: 0.25 }}
          className="w-32 h-32 rounded-full border-4 border-white shadow-2xl overflow-hidden bg-white/10 z-10"
        >
          {theirPhoto
            ? <img src={theirPhoto} alt={matchUser.name} className="w-full h-full object-cover" />
            : <div className="w-full h-full flex items-center justify-center text-4xl">😍</div>}
        </motion.div>
      </div>

      <motion.p
        className="text-white/80 text-sm text-center no-translate"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.55 }}
      >
        Вы и <span className="font-semibold text-white">{matchUser.name}</span> понравились друг другу
      </motion.p>

      <motion.div
        className="w-full max-w-xs mt-8 space-y-3"
        initial={{ y: 40, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.65 }}
      >
        <button
          data-testid="match-say-hi"
          onClick={() => nav(`/chats/${matchUser.user_id}`)}
          className="w-full py-3.5 rounded-full bg-primary text-white font-semibold flex items-center justify-center gap-2 active:scale-95 transition-transform shadow-lg shadow-primary/30"
        >
          <MessageCircle className="w-5 h-5" /> Написать сообщение
        </button>
        <button
          data-testid="match-continue"
          onClick={onClose}
          className="w-full py-3 rounded-full bg-white/10 text-white/90 font-medium border border-white/20 active:scale-95 transition-transform"
        >
          Продолжить поиск
        </button>
      </motion.div>
    </motion.div>
  );
};
