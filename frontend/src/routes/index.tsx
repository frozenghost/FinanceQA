import { createRoute, useNavigate, useSearch } from "@tanstack/react-router";
import { useState, useEffect } from "react";
import { Send, TrendingUp } from "lucide-react";
import { rootRoute } from "./__root";
import { chatStorage } from "../services/chatStorage";

function WelcomePage() {
  const navigate = useNavigate();
  const search = useSearch({ from: indexRoute.id });
  const [input, setInput] = useState("");
  const [isRedirecting, setIsRedirecting] = useState(true);

  useEffect(() => {
    const initAndRedirect = async () => {
      try {
        await chatStorage.init();
        const convs = await chatStorage.getConversations();
        if (convs.length > 0 && !search.new) {
          navigate({
            to: "/chat/$conversationId",
            params: { conversationId: convs[0].id },
            replace: true,
          });
          return;
        }
      } catch (e) {
        console.error("Failed to init or redirect:", e);
      }
      setIsRedirecting(false);
    };
    initAndRedirect();
  }, [navigate, search.new]);

  const startConversation = async (message: string) => {
    if (!message.trim()) return;
    try {
      await chatStorage.init();
      const convId = await chatStorage.createConversation(message.trim());
      navigate({
        to: "/chat/$conversationId",
        params: { conversationId: convId },
        state: { initialMessage: message.trim() },
      });
    } catch (e) {
      console.error("Failed to create conversation:", e);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    startConversation(input.trim());
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  if (isRedirecting) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="flex gap-2 items-center text-slate-400">
          <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce" />
          <div
            className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce"
            style={{ animationDelay: "150ms" }}
          />
          <div
            className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce"
            style={{ animationDelay: "300ms" }}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-slate-950/60">
      <div className="flex-1 overflow-y-auto px-4 py-8">
        <div className="max-w-3xl mx-auto">
          <div className="flex flex-col items-center justify-center min-h-[60vh] animate-in fade-in slide-in-from-bottom-4 duration-700">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-6 shadow-[0_22px_55px_rgba(16,185,129,0.75)] border border-emerald-400/70 bg-slate-950">
              <TrendingUp className="w-8 h-8 text-emerald-400" strokeWidth={2} />
            </div>
            <h1 className="text-2xl font-semibold text-slate-50 mb-3 tracking-tight">
              Hi, I'm your financial assistant
            </h1>
            <p className="text-slate-400 mb-8 max-w-md text-center leading-relaxed">
              I can analyze stock quotes, explain technical indicators, get the latest market news, or answer questions about financial concepts.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full max-w-2xl">
              {[
                { title: "Quote Query", desc: "How has AAPL performed this week?" },
                { title: "Technical Analysis", desc: "Show me TSLA's technicals" },
                { title: "Q&A", desc: "What is P/E ratio?" },
                { title: "Market News", desc: "Latest news about NVIDIA" },
              ].map((q) => (
                <button
                  key={q.title}
                  onClick={() => startConversation(q.desc)}
                  className="flex flex-col text-left p-4 rounded-2xl border border-slate-700/80 bg-slate-900/70 backdrop-blur-2xl hover:border-emerald-400/80 hover:bg-slate-900/90 hover:shadow-[0_22px_60px_rgba(15,23,42,0.9)] transition-all duration-200 group"
                >
                  <span className="font-semibold text-slate-100 group-hover:text-emerald-300 mb-1">
                    {q.title}
                  </span>
                  <span className="text-sm text-slate-400 group-hover:text-slate-200">
                    {q.desc}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="p-4 bg-linear-to-t from-slate-950/95 via-slate-950/80 to-transparent pt-6">
        <div className="max-w-3xl mx-auto">
          <form
            onSubmit={handleSubmit}
            className="relative bg-slate-950/80 border border-slate-700/80 rounded-2xl shadow-[0_22px_65px_rgba(15,23,42,0.95)] focus-within:border-emerald-400/80 focus-within:shadow-[0_26px_80px_rgba(16,185,129,0.7)] transition-all duration-200 backdrop-blur-2xl"
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Send a message (Shift + Enter for new line)..."
              className="w-full bg-transparent px-5 py-4 pr-16 text-slate-50 placeholder:text-slate-500 focus:outline-none resize-none min-h-[60px] max-h-32 overflow-y-auto block rounded-2xl"
              rows={1}
            />
            <div className="absolute right-2 bottom-2">
              <button
                type="submit"
                disabled={!input.trim()}
                className="p-2.5 bg-emerald-500 text-slate-950 hover:bg-emerald-400 disabled:bg-slate-700 disabled:text-slate-400 rounded-xl transition-colors shadow-[0_16px_40px_rgba(16,185,129,0.7)] disabled:shadow-none border border-emerald-400/80 disabled:border-slate-600/80"
                title="Send"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
          </form>
          <div className="text-center mt-3 text-xs text-slate-500 font-medium">
            AI-generated information is for reference only and does not constitute any investment advice.
          </div>
        </div>
      </div>
    </div>
  );
}

export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  validateSearch: (s: Record<string, unknown>) => ({
    new: s.new === "1" || s.new === true,
  }),
  component: WelcomePage,
});
