import { Link } from "@tanstack/react-router";
import { MessageSquare, History, Plus, BarChart3 } from "lucide-react";

const navLinkClass =
  "flex items-center gap-3 px-3 py-2.5 rounded-2xl text-sm font-medium text-slate-300 transition-all hover:bg-slate-900/70 hover:text-emerald-300 hover:shadow-[0_14px_40px_rgba(15,23,42,0.9)]";
const navLinkActiveClass =
  "bg-slate-900 text-emerald-300 shadow-[0_18px_48px_rgba(15,23,42,0.95)] border border-emerald-400/50";

interface Props {
  onNewChat: () => void;
}

export function Sidebar({ onNewChat }: Props) {
  return (
    <aside className="w-[260px] flex flex-col shrink-0 rounded-3xl bg-slate-950/80 border border-emerald-500/25 backdrop-blur-2xl shadow-[0_24px_70px_rgba(15,23,42,0.98)]">
      <div className="p-5 flex items-center gap-2.5 text-slate-50 font-semibold text-xl tracking-tight">
        <div className="bg-slate-900 rounded-2xl p-1.5 shadow-[0_0_26px_rgba(16,185,129,0.9)] border border-emerald-500/40">
          <BarChart3 className="w-5 h-5 text-emerald-400" />
        </div>
        <span className="tracking-[0.08em] text-sm font-semibold uppercase text-slate-300">
          Finance
          <span className="text-emerald-400 ml-0.5">QA</span>
        </span>
      </div>

      <div className="px-4 py-3">
        <button
          type="button"
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 bg-emerald-500 text-slate-950 hover:bg-emerald-400 hover:text-slate-950 px-4 py-2.5 rounded-2xl transition-all font-medium text-sm shadow-[0_18px_46px_rgba(16,185,129,0.75)] active:scale-[0.98] border border-emerald-400/70"
          aria-label="Start new chat"
        >
          <Plus className="w-4 h-4" />
          New Chat
        </button>
      </div>

      <nav className="flex-1 px-3 space-y-1.5 overflow-y-auto mt-1 pb-3">
        <Link
          to="/"
          search={{ new: false }}
          className={navLinkClass}
          activeProps={{ className: navLinkActiveClass }}
        >
          <MessageSquare className="w-4 h-4" />
          Current Chat
        </Link>
        <Link
          to="/history"
          className={navLinkClass}
          activeProps={{ className: navLinkActiveClass }}
        >
          <History className="w-4 h-4" />
          History
        </Link>
      </nav>
    </aside>
  );
}
