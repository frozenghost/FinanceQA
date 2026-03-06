import { createRoute, useNavigate, useRouterState } from "@tanstack/react-router";
import { useState, useRef, useEffect } from "react";
import { Send, Square } from "lucide-react";
import { rootRoute } from "./__root";
import { useSSEChat } from "../hooks/useSSEChat";
import { MessageRenderer } from "../components/MessageRenderer";
import { chatStorage } from "../services/chatStorage";

const CHAT_OPTIONS_SKIP = { skipInitialLoad: true } as const;
const CHAT_OPTIONS_LOAD = { skipInitialLoad: false } as const;

function ConversationPage() {
  const { conversationId } = conversationRoute.useParams();
  const navigate = useNavigate();
  const locationState = useRouterState({ select: (s) => s.location.state });
  const hasInitialMessage = !!locationState?.initialMessage;
  const chatOptions = hasInitialMessage ? CHAT_OPTIONS_SKIP : CHAT_OPTIONS_LOAD;
  const { messages, isLoading, send, stop } = useSSEChat(conversationId, chatOptions);
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
        try {
          await chatStorage.init();
          await send(initialMessage);
        } catch (err) {
          console.error("Failed to send initial message:", err);
        }
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
      // Already on a conversation page: continue sending in current session
      if (conversationId) {
        await send(text);
      } else {
        // No conversation ID: create new session and navigate
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
          {messages.map((m, index) => {
            const isLast = index === messages.length - 1;
            const isLastAssistant = isLast && m.role === "assistant";

            return (
              <MessageRenderer
                key={m.id}
                message={m}
                isThinking={isLoading && isLastAssistant}
              />
            );
          })}
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
              placeholder="Send a message (Shift + Enter for new line)..."
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
                  title="Stop generating"
                >
                  <Square className="w-5 h-5 fill-slate-400" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!input.trim()}
                  className="p-2.5 bg-emerald-500 text-slate-950 hover:bg-emerald-400 disabled:bg-slate-700 disabled:text-slate-400 rounded-xl transition-colors shadow-[0_16px_40px_rgba(16,185,129,0.7)] disabled:shadow-none border border-emerald-400/80 disabled:border-slate-600/80"
                  title="Send"
                >
                  <Send className="w-5 h-5" />
                </button>
              )}
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

export const conversationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/chat/$conversationId",
  component: ConversationPage,
});
