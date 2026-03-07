import { createRoute, useNavigate } from "@tanstack/react-router";
import { rootRoute } from "./__root";
import { Clock, Trash2, MessageSquare, ChevronRight } from "lucide-react";
import { useChatHistory } from "../hooks/useChatHistory";
import { useState } from "react";

function HistoryPage() {
  const navigate = useNavigate();
  const { conversations, isLoading, deleteConversation, clearAll } =
    useChatHistory();
  const [showConfirm, setShowConfirm] = useState(false);

  const handleOpenConversation = (conversationId: string) => {
    navigate({ to: "/chat/$conversationId", params: { conversationId } });
  };

  const handleDelete = async (
    e: React.MouseEvent,
    conversationId: string
  ) => {
    e.stopPropagation();
    if (confirm("Are you sure you want to delete this conversation?")) {
      await deleteConversation(conversationId);
    }
  };

  const handleClearAll = async () => {
    await clearAll();
    setShowConfirm(false);
  };

  const formatDate = (timestamp: number) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) {
      return date.toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
      });
    } else if (days === 1) {
      return "Yesterday";
    } else if (days < 7) {
      return `${days} days ago`;
    } else {
      return date.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      });
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-950/60">
      <div className="flex-1 min-h-0 overflow-y-auto px-8 py-10 max-w-4xl mx-auto w-full">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-slate-50 tracking-tight">
              History
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              {conversations.length} conversation{conversations.length !== 1 ? "s" : ""} total
            </p>
          </div>
          {conversations.length > 0 && (
            <button
              onClick={() => setShowConfirm(true)}
              className="flex items-center gap-2 px-4 py-2 text-sm text-pink-300 bg-slate-900/70 border border-pink-500/40 hover:bg-pink-500/10 hover:border-pink-500/60 rounded-xl transition-all font-medium shadow-lg"
            >
              <Trash2 className="w-4 h-4" />
              Clear All
            </button>
          )}
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-24">
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
              <span className="ml-2 text-sm">Loading...</span>
            </div>
          </div>
        ) : conversations.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 bg-slate-900/40 rounded-3xl border border-slate-800/70 border-dashed">
            <div className="w-16 h-16 bg-slate-900 border border-slate-700/80 text-slate-400 rounded-2xl flex items-center justify-center mb-5 rotate-3 shadow-lg">
              <Clock className="w-8 h-8" />
            </div>
            <h3 className="text-lg font-semibold text-slate-200 mb-2">
              No history yet
            </h3>
            <p className="text-slate-400 text-sm max-w-sm text-center leading-relaxed">
              Start a new conversation and your chat history will be saved here automatically.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {conversations.map((conv) => (
              <button
                key={conv.id}
                onClick={() => handleOpenConversation(conv.id)}
                className="w-full flex items-center gap-4 p-4 bg-slate-900/70 border border-slate-800/70 hover:border-emerald-500/50 hover:bg-slate-900/90 rounded-2xl transition-all group text-left shadow-lg hover:shadow-[0_20px_50px_rgba(15,23,42,0.9)]"
              >
                <div className="w-10 h-10 bg-slate-950 border border-slate-700/80 rounded-xl flex items-center justify-center shrink-0 group-hover:border-emerald-500/50 transition-colors">
                  <MessageSquare className="w-5 h-5 text-slate-400 group-hover:text-emerald-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-slate-100 font-medium truncate group-hover:text-emerald-300 transition-colors">
                    {conv.title}
                  </h3>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                    <span>{conv.messageCount} message{conv.messageCount !== 1 ? "s" : ""}</span>
                    <span>•</span>
                    <span>{formatDate(conv.updatedAt)}</span>
                  </div>
                </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={(e) => handleDelete(e, conv.id)}
                      className="p-2 text-slate-500 hover:text-pink-300 hover:bg-pink-500/10 rounded-lg transition-colors"
                      title="Delete"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                    <ChevronRight className="w-5 h-5 text-slate-600 group-hover:text-emerald-400 transition-colors" />
                  </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Confirm clear dialog */}
      {showConfirm && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-slate-900 border border-slate-700/80 rounded-2xl p-6 max-w-md w-full mx-4 shadow-[0_30px_80px_rgba(15,23,42,0.95)]">
            <h3 className="text-lg font-semibold text-slate-50 mb-2">
              Clear all history?
            </h3>
            <p className="text-sm text-slate-400 mb-6">
              This will permanently delete all conversations and cannot be undone.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowConfirm(false)}
                className="flex-1 px-4 py-2.5 bg-slate-800 text-slate-200 hover:bg-slate-700 rounded-xl transition-colors font-medium"
              >
                Cancel
              </button>
              <button
                onClick={handleClearAll}
                className="flex-1 px-4 py-2.5 bg-rose-500 text-white hover:bg-rose-600 rounded-xl transition-colors font-medium shadow-lg"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export const historyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/history",
  component: HistoryPage,
});