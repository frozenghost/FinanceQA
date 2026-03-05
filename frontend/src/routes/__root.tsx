import { createRootRoute, Outlet, Link, useNavigate } from "@tanstack/react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MessageSquare, History, Plus, BarChart3, Settings } from "lucide-react";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 2,
    },
  },
});

function RootLayout() {
  const navigate = useNavigate();

  const handleNewChat = () => {
    navigate({ to: "/" });
  };

  return (
    <QueryClientProvider client={queryClient}>
      <div className="flex h-screen text-slate-100 font-sans overflow-hidden px-4 py-4">
        {/* Sidebar */}
        <aside className="w-[260px] flex flex-col shrink-0 rounded-3xl bg-slate-950/70 border border-emerald-500/20 backdrop-blur-2xl shadow-[0_24px_70px_rgba(15,23,42,0.95)]">
          <div className="p-5 flex items-center gap-2.5 text-slate-50 font-semibold text-xl tracking-tight">
            <div className="bg-slate-900 rounded-2xl p-1.5 shadow-[0_0_24px_rgba(16,185,129,0.9)]">
              <BarChart3 className="w-5 h-5 text-emerald-400" />
            </div>
            <span>FinanceQA</span>
          </div>

          <div className="px-4 py-3">
            <button
              onClick={handleNewChat}
              className="w-full flex items-center justify-center gap-2 bg-emerald-500 text-slate-950 hover:bg-emerald-400 hover:text-slate-950 px-4 py-2.5 rounded-2xl transition-all font-medium text-sm shadow-[0_16px_40px_rgba(16,185,129,0.7)] active:scale-[0.98]"
            >
              <Plus className="w-4 h-4" />
              开启新对话
            </button>
          </div>

          <nav className="flex-1 px-3 space-y-1.5 overflow-y-auto mt-1 pb-3">
            <Link
              to="/"
              className="flex items-center gap-3 px-3 py-2.5 rounded-2xl text-sm font-medium text-slate-300 transition-all hover:bg-slate-900/70 hover:text-emerald-300 hover:shadow-[0_14px_40px_rgba(15,23,42,0.9)]"
              activeProps={{
                className:
                  "bg-slate-900 text-emerald-300 shadow-[0_18px_48px_rgba(15,23,42,0.95)] border border-emerald-400/40",
              }}
            >
              <MessageSquare className="w-4 h-4" />
              当前对话
            </Link>
            <Link
              to="/history"
              className="flex items-center gap-3 px-3 py-2.5 rounded-2xl text-sm font-medium text-slate-300 transition-all hover:bg-slate-900/70 hover:text-emerald-300 hover:shadow-[0_14px_40px_rgba(15,23,42,0.9)]"
              activeProps={{
                className:
                  "bg-slate-900 text-emerald-300 shadow-[0_18px_48px_rgba(15,23,42,0.95)] border border-emerald-400/40",
              }}
            >
              <History className="w-4 h-4" />
              历史记录
            </Link>
          </nav>

          <div className="p-4 border-t border-slate-800/80 mx-3 mt-0">
            <button className="flex items-center gap-2 px-2.5 py-2.5 w-full text-xs font-medium text-slate-400 hover:text-emerald-300 hover:bg-slate-900/70 rounded-2xl transition-all hover:shadow-[0_10px_26px_rgba(15,23,42,0.9)]">
              <Settings className="w-4 h-4 text-slate-500" />
              系统设置
            </button>
          </div>
        </aside>

        {/* Main Content */}
        <main className="flex-1 flex flex-col relative min-w-0 ml-4 rounded-3xl overflow-hidden border border-slate-800/70 bg-slate-950/60 backdrop-blur-3xl shadow-[0_26px_70px_rgba(15,23,42,0.95)]">
          <Outlet />
        </main>
      </div>
    </QueryClientProvider>
  );
}

export const rootRoute = createRootRoute({
  component: RootLayout,
});
