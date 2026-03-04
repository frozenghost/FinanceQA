import { createRootRoute, Outlet, Link } from "@tanstack/react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MessageSquare, History } from "lucide-react";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 2,
    },
  },
});

function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-slate-50 text-slate-800">
        {/* Header */}
        <header className="border-b border-slate-200 bg-white/80 backdrop-blur sticky top-0 z-10">
          <div className="max-w-4xl mx-auto px-4 h-14 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <MessageSquare className="w-5 h-5 text-blue-500" />
              <span className="font-semibold text-lg text-slate-800">Finance QA</span>
              <span className="text-xs text-slate-500 ml-1 bg-slate-100 px-1.5 py-0.5 rounded-md border border-slate-200">v0.1</span>
            </div>
            <nav className="flex gap-4 text-sm">
              <Link
                to="/"
                className="flex items-center gap-1 text-slate-500 hover:text-slate-900 transition-colors"
                activeProps={{ className: "text-slate-900 font-medium" }}
              >
                <MessageSquare className="w-4 h-4" />
                对话
              </Link>
              <Link
                to="/history"
                className="flex items-center gap-1 text-slate-500 hover:text-slate-900 transition-colors"
                activeProps={{ className: "text-slate-900 font-medium" }}
              >
                <History className="w-4 h-4" />
                历史
              </Link>
            </nav>
          </div>
        </header>

        {/* Page content */}
        <Outlet />
      </div>
    </QueryClientProvider>
  );
}

export const rootRoute = createRootRoute({
  component: RootLayout,
});
