import { createRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Send, Square } from "lucide-react";
import { rootRoute } from "./__root";
import { useSSEChat } from "../hooks/useSSEChat";
import { MessageRenderer } from "../components/MessageRenderer";

function ChatPage() {
  const { messages, isLoading, send, stop } = useSSEChat();
  const [input, setInput] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    send(input.trim());
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)] max-w-3xl mx-auto">
      {/* Messages area */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-3">
            <MessageSquareIcon />
            <p className="text-lg font-medium text-slate-700">金融资产问答系统</p>
            <p className="text-sm text-center max-w-md text-slate-500">
              支持股票行情查询、技术分析、金融知识检索、新闻获取等。
              <br />
              试试问："BABA 最近 7 天涨跌情况如何？"
            </p>
            <div className="flex gap-2 mt-4 flex-wrap justify-center">
              {[
                "BABA 最近 7 天涨跌如何？",
                "什么是市盈率？",
                "TSLA 技术面分析",
                "特斯拉最新新闻",
              ].map((q) => (
                <button
                  key={q}
                  onClick={() => send(q)}
                  className="text-xs bg-white text-slate-600 border border-slate-200 shadow-sm rounded-full px-4 py-2 hover:border-blue-300 hover:text-blue-600 transition-all duration-200"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <MessageRenderer key={m.id} message={m} />
        ))}

        {isLoading && (
          <div className="flex items-center gap-2 text-slate-500 text-sm px-4">
            <div className="animate-typing flex gap-1">
              <span className="w-1.5 h-1.5 bg-blue-500 rounded-full"></span>
              <span className="w-1.5 h-1.5 bg-blue-500 rounded-full"></span>
              <span className="w-1.5 h-1.5 bg-blue-500 rounded-full"></span>
            </div>
            <span className="text-slate-500 font-medium">Agent 分析中...</span>
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="border-t border-slate-200 bg-white p-4">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入问题，例如：BABA 最近 7 天涨跌情况如何？"
            className="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:bg-white focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 placeholder:text-slate-400 text-slate-800 transition-all duration-200 shadow-sm"
            disabled={isLoading}
          />
          {isLoading ? (
            <button
              type="button"
              onClick={stop}
              className="px-5 py-3 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-xl text-sm font-medium flex items-center gap-2 transition-all duration-200"
            >
              <Square className="w-4 h-4" />
              停止
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="px-5 py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-100 disabled:text-slate-400 disabled:shadow-none text-white rounded-xl text-sm font-medium flex items-center gap-2 transition-all duration-200 shadow-sm"
            >
              <Send className="w-4 h-4" />
              发送
            </button>
          )}
        </form>
      </div>
    </div>
  );
}

function MessageSquareIcon() {
  return (
    <svg
      className="w-12 h-12 text-blue-200"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
      />
    </svg>
  );
}

export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: ChatPage,
});
