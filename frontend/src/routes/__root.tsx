import { createRootRoute, Outlet, useNavigate } from "@tanstack/react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { Sidebar } from "../components/Sidebar";

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
    navigate({ to: "/", search: { new: true } });
  };

  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
      <div className="flex h-screen text-slate-100 font-sans overflow-hidden px-4 py-4">
        <Sidebar onNewChat={handleNewChat} />

        <main className="flex-1 flex flex-col relative min-w-0 ml-4 rounded-3xl overflow-hidden border border-slate-800/70 bg-slate-950/70 backdrop-blur-3xl shadow-[0_30px_80px_rgba(15,23,42,0.98)]">
          <Outlet />
        </main>
      </div>
      </ErrorBoundary>
    </QueryClientProvider>
  );
}

export const rootRoute = createRootRoute({
  component: RootLayout,
});
