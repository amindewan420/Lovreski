import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";

/**
 * Bottom-sheet modal used for dropdowns and pickers across the profile.
 * Slides up from the bottom on mobile, centers on desktop.
 */
export const BottomSheet = ({ open, onClose, title, children, testId }) => (
  <AnimatePresence>
    {open && (
      <motion.div
        data-testid={testId}
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-[70] flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      >
        <motion.div
          onClick={(e) => e.stopPropagation()}
          initial={{ y: 60, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 60, opacity: 0 }}
          transition={{ type: "spring", damping: 22 }}
          className="w-full sm:max-w-md bg-card border-t sm:border sm:rounded-2xl border-border shadow-2xl rounded-t-3xl max-h-[85vh] overflow-hidden flex flex-col"
        >
          <div className="flex items-center justify-between px-5 py-4 border-b border-border">
            <h3 className="font-display font-black text-lg">{title}</h3>
            <button onClick={onClose} className="p-1 rounded-full hover:bg-muted"><X className="w-5 h-5" /></button>
          </div>
          <div className="p-5 overflow-y-auto">{children}</div>
        </motion.div>
      </motion.div>
    )}
  </AnimatePresence>
);
