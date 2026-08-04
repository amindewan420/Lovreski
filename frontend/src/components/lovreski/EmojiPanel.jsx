import { useState } from "react";
import { X } from "lucide-react";

const CATEGORIES = [
  { key: "faces", label: "😀", items: ['😀','😃','😄','😁','😆','😅','😂','🤣','😊','😇','🥰','😍','🤩','😘','😗','☺️','😚','😙','🥲','😋','😛','😜','🤪','😝','🤑','🤗','🤭','🤫','🤔','🤐','🤨','😐','😑','😶','😏','😒','🙄','😬','🤥','😌','😔','😪','🤤','😴','😷','🤒','🤕','🤢','🤮','🤧','🥵','🥶','🥴','😵','🤯','🤠','🥳','🥸','😎','🤓','🧐','😕','😟','🙁','☹️','😮','😯','😲','😳','🥺','😦','😧','😨','😰','😥','😢','😭','😱','😖','😣','😞','😓','😩','😫','🥱','😤','😡','😠'] },
  { key: "love",  label: "❤️", items: ['❤️','🧡','💛','💚','💙','💜','🖤','🤍','🤎','💔','❣️','💕','💞','💓','💗','💖','💘','💝','💟','💋','💌','💍','💎','💒','👰','🤵','💑','👫','👬','👭','💏','🥂','🌹','🌷','🌸','🌺','🌻','🌼','⭐','🌟','💫','✨','🎆','🎇','🎉','🎊','🎈','🎀'] },
  { key: "gest",  label: "👋", items: ['👋','🤚','🖐️','✋','🖖','👌','🤌','🤏','✌️','🤞','🤟','🤘','🤙','👈','👉','👆','🖕','👇','☝️','👍','👎','✊','👊','🤛','🤜','👏','🙌','👐','🤲','🤝','🙏','✍️','💅','🤳','💪','🦾','🦿','🦵','🦶','👃','👂','🦻','👁️','👅','🦷','👀','🧠'] },
  { key: "act",   label: "🎭", items: ['⚽','🏀','🏈','⚾','🥎','🎾','🏐','🏉','🥏','🎱','🏓','🏸','⛳','🎯','🎳','🏹','🎣','🤿','🥊','🥋','🎽','🛹','🛷','⛸️','🏋️','🤼','🤸','🏆','🥇','🥈','🥉','🏅','🎖️','🎪','🤹','🎭','🎨','🎬','🎤','🎧'] },
  { key: "food",  label: "🍕", items: ['🍎','🍊','🍋','🍇','🍓','🫐','🍒','🍑','🥭','🍍','🥥','🥝','🍅','🍆','🥑','🌽','🌶️','🥦','🧀','🥚','🍳','🥞','🧇','🥓','🍔','🍟','🍕','🌮','🌯','🍱','🍣','🍜','🍝','🍛','🍲','🥗','🧁','🍰','🎂','🍩','🍪','🍫','🍬','🍭','☕','🍵','🧃','🍺'] },
  { key: "trav",  label: "🌍", items: ['🚗','🚕','🚙','🚌','🏎️','🚓','🚑','🚒','🛻','🚚','🚛','🚜','🏍️','🛵','🚲','🛴','⛵','🚤','🛥️','🚢','✈️','🛩️','🛫','🛬','🚁','🚀','🛸','🌍','🌎','🌏','🗺️','🧭','🏔️','⛰️','🌋','🗻','🏕️','🏖️','🏜️','🏝️','🏟️','🏛️','🏗️','🏘️','🏚️','🏠','🏡','🏢'] },
];

export default function EmojiPanel({ open, onClose, onPick }) {
  const [tab, setTab] = useState("faces");
  if (!open) return null;
  const active = CATEGORIES.find((c) => c.key === tab) || CATEGORIES[0];
  return (
    <div className="fixed inset-0 z-[60] flex items-end" data-testid="emoji-sheet">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-md mx-auto bg-white rounded-t-3xl flex flex-col" style={{ maxHeight: "60vh", height: "60vh" }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
          <p className="text-sm font-semibold text-slate-700">Эмодзи</p>
          <button data-testid="emoji-close" onClick={onClose} className="p-1 rounded-full hover:bg-slate-100"><X className="w-4 h-4 text-slate-500" /></button>
        </div>
        <div className="flex gap-1 px-2 py-2 border-b border-slate-100 overflow-x-auto">
          {CATEGORIES.map((c) => (
            <button key={c.key} data-testid={`emoji-tab-${c.key}`} onClick={() => setTab(c.key)}
              className={`px-3 py-1.5 text-xl rounded-full ${tab === c.key ? "bg-primary/15" : "hover:bg-slate-100"}`}>{c.label}</button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          <div className="grid grid-cols-6 sm:grid-cols-8 gap-1">
            {active.items.map((e, i) => (
              <button key={`${active.key}-${i}`} data-testid={`emoji-${e}`} onClick={() => onPick?.(e)}
                className="text-2xl h-10 rounded hover:bg-slate-100 active:scale-90 transition-transform">{e}</button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
