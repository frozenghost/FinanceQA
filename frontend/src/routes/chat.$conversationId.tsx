import { createRoute, useNavigate, useRouterState } from "@tanstack/react-router";
import { useState, useRef, useEffect } from "react";
import { Send, Square, Sparkles } from "lucide-react";
import { rootRoute } from "./__root";
import { useSSEChat } from "../hooks/useSSEChat";
import { MessageRenderer } from "../components/MessageRenderer";
import { chatStorage } from "../services/chatStorage";

function ConversationPage() {
  const { conversationId } = conversationRoute.useParams();
  const navigate = useNavigate();
  const locationState = useRouterState({ select: (s) => s.location.state });
  const hasInitialMessage = !!locationState?.initialMessage;
  const { messages, isLoading, send, stop } = useSSEChat(conversationId, {
    skipInitialLoad: hasInitialMessage,
  });
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const initialMessageSent = useRef(false);
  const prevLoadingRef = useRef(false);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  useEffect(() => {
    const initialMessage = locationState?.initialMessage;
    if (
      initialMessage &&
      conversationId &&
      !initialMessageSent.current
    ) {
      initialMessageSent.current = true;
      (async () => {
        await chatStorage.init();
        send(initialMessage);
      })();
    }
  }, [conversationId, locationState?.initialMessage, send]);

  useEffect(() => {
    const wasLoading = prevLoadingRef.current;
    prevLoadingRef.current = isLoading;
    if (
      initialMessageSent.current &&
      locationState?.initialMessage &&
      wasLoading &&
      !isLoading
    ) {
      navigate({
        to: "/chat/$conversationId",
        params: { conversationId },
        replace: true,
        state: undefined,
      });
    }
  }, [isLoading, conversationId, locationState?.initialMessage, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    const text = input.trim();
    setInput("");
    try {
      // 已在某个对话页：继续在当前会话中发送
      if (conversationId) {
        await send(text);
      } else {
        // 没有会话 ID 时，新建会话并跳转
        await chatStorage.init();
        const newId = await chatStorage.createConversation(text);
        navigate({
          to: "/chat/$conversationId",
          params: { conversationId: newId },
          state: { initialMessage: text },
        });
      }
    } catch (err) {
      console.error("Failed to send message:", err);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-950/60">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4 py-8">
        <div className="max-w-3xl mx-auto space-y-8">
          {messages.map((m) => (
            <MessageRenderer key={m.id} message={m} />
          ))}
          {isLoading && (
            <div className="flex items-start gap-4 animate-in fade-in duration-300">
              <div className="w-8 h-8 rounded-full bg-slate-950 flex items-center justify-center shrink-0 mt-1 shadow-[0_12px_32px_rgba(16,185,129,0.6)] ring-2 ring-emerald-400/80">
                <Sparkles className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="flex items-center h-10 gap-2 text-slate-400 text-sm">
                <div className="flex gap-1.5 items-center bg-slate-900/80 px-4 py-2.5 rounded-full border border-slate-700/80 shadow-[0_18px_45px_rgba(15,23,42,0.9)] backdrop-blur-2xl">
                  <span
                    className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce"
                    style={{ animationDelay: "0ms" }}
                  ></span>
                  <span
                    className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce"
                    style={{ animationDelay: "150ms" }}
                  ></span>
                  <span
                    className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce"
                    style={{ animationDelay: "300ms" }}
                  ></span>
                  <span className="ml-1.5 font-medium text-xs text-slate-300">
                    正在思考...
                  </span>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} className="h-4" />
        </div>
      </div>

      {/* Input Area */}
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
              placeholder="发送消息 (Shift + Enter 换行)..."
              className="w-full bg-transparent px-5 py-4 pr-16 text-slate-50 placeholder:text-slate-500 focus:outline-none resize-none min-h-[60px] max-h-32 overflow-y-auto block rounded-2xl"
              rows={1}
              disabled={isLoading}
            />
            <div className="absolute right-2 bottom-2">
              {isLoading ? (
                <button
                  type="button"
                  onClick={stop}
                  className="p-2.5 bg-slate-800/80 text-slate-200 hover:bg-slate-700 rounded-xl transition-colors border border-slate-600/80"
                  title="停止生成"
                >
                  <Square className="w-5 h-5 fill-slate-400" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!input.trim()}
                  className="p-2.5 bg-emerald-500 text-slate-950 hover:bg-emerald-400 disabled:bg-slate-700 disabled:text-slate-400 rounded-xl transition-colors shadow-[0_16px_40px_rgba(16,185,129,0.7)] disabled:shadow-none border border-emerald-400/80 disabled:border-slate-600/80"
                  title="发送"
                >
                  <Send className="w-5 h-5" />
                </button>
              )}
            </div>
          </form>
          <div className="text-center mt-3 text-xs text-slate-500 font-medium">
            AI 提供的信息仅供参考，不构成任何投资建议。
          </div>
        </div>
      </div>
    </div>
  );
}

export const conversationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/chat/$conversationId",
  component: ConversationPage,
});
