/**
 * MessageRenderer — renders chat messages with Markdown, data cards, and step folding.
 */

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { clsx } from "clsx";
import {
  User,
  Bot,
  ChevronDown,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Minus,
} from "lucide-react";
import type { Message, MessageMetadata } from "../hooks/useSSEChat";
import { PriceChart } from "./PriceChart";

interface Props {
  message: Message;
}

export function MessageRenderer({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div
      className={clsx(
        "flex gap-3",
        isUser ? "justify-end" : "justify-start"
      )}
    >
      {/* Avatar */}
      {!isUser && (
        <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center flex-shrink-0 mt-0.5 shadow-sm border border-blue-200">
          <Bot className="w-5 h-5" />
        </div>
      )}

      <div
        className={clsx(
          "max-w-[85%] rounded-2xl px-5 py-3.5 text-sm shadow-sm",
          isUser
            ? "bg-blue-50 text-blue-900 border border-blue-100 rounded-tr-sm"
            : "bg-white text-slate-800 border border-slate-200 rounded-tl-sm"
        )}
      >
        {/* Message content */}
        {message.content && (
          <div className="prose prose-slate prose-sm max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {/* Metadata cards */}
        {message.metadata && <MetadataCards metadata={message.metadata} />}
      </div>

      {/* User avatar */}
      {isUser && (
        <div className="w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center flex-shrink-0 mt-0.5 shadow-sm">
          <User className="w-4 h-4" />
        </div>
      )}
    </div>
  );
}

function MetadataCards({ metadata }: { metadata: MessageMetadata }) {
  return (
    <div className="mt-3 space-y-3">
      {/* Market data card */}
      {metadata.type === "market" && metadata.ticker && (
        <MarketCard metadata={metadata} />
      )}

      {/* Technical indicators card */}
      {metadata.type === "technical" && metadata.indicators && (
        <TechnicalCard metadata={metadata} />
      )}

      {/* Agent reasoning steps */}
      {metadata.steps && metadata.steps.length > 0 && (
        <StepsFold steps={metadata.steps} />
      )}
    </div>
  );
}

function MarketCard({ metadata }: { metadata: MessageMetadata }) {
  const trendIcon =
    metadata.trend === "上涨" ? (
      <TrendingUp className="w-4 h-4 text-green-500" />
    ) : metadata.trend === "下跌" ? (
      <TrendingDown className="w-4 h-4 text-red-500" />
    ) : (
      <Minus className="w-4 h-4 text-yellow-500" />
    );

  const changeColor =
    (metadata.change_pct ?? 0) > 0
      ? "text-green-600"
      : (metadata.change_pct ?? 0) < 0
        ? "text-red-600"
        : "text-slate-500";

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-mono font-semibold text-slate-800 text-base">{metadata.ticker}</span>
          {trendIcon}
        </div>
        <span className="text-xl font-bold text-slate-800">
          ${metadata.current?.toFixed(2)}
        </span>
      </div>
      <div className="flex items-center gap-1.5 bg-slate-50 w-fit px-2 py-1 rounded-md">
        <span className={clsx("text-sm font-medium", changeColor)}>
          {(metadata.change_pct ?? 0) > 0 ? "+" : ""}
          {metadata.change_pct?.toFixed(2)}%
        </span>
        <span className="text-xs text-slate-500 font-medium">{metadata.trend}</span>
      </div>

      {/* Price chart */}
      {metadata.ohlcv && metadata.ohlcv.length > 0 && (
        <div className="mt-3">
          <PriceChart data={metadata.ohlcv} ticker={metadata.ticker || ""} />
        </div>
      )}
    </div>
  );
}

function TechnicalCard({ metadata }: { metadata: MessageMetadata }) {
  const indicators = metadata.indicators || {};
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
      <div className="text-xs text-slate-500 mb-3 font-semibold uppercase tracking-wider">技术指标</div>
      <div className="grid grid-cols-3 gap-3 text-xs">
        {Object.entries(indicators).map(([key, value]) => (
          <div key={key} className="bg-slate-50 rounded-lg p-2.5 border border-slate-100">
            <div className="text-slate-500 font-medium">{key}</div>
            <div className="font-mono font-semibold text-slate-800 mt-1">
              {value !== null ? value : "N/A"}
            </div>
          </div>
        ))}
      </div>
      {metadata.signals && metadata.signals.length > 0 && (
        <div className="mt-3 space-y-1.5 bg-blue-50/50 p-2.5 rounded-lg border border-blue-100/50">
          {metadata.signals.map((signal, i) => (
            <div key={i} className="text-xs text-slate-600 flex items-start gap-1.5">
              <span className="text-blue-500 mt-0.5">•</span>
              {signal}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StepsFold({ steps }: { steps: MessageMetadata["steps"] }) {
  const [open, setOpen] = useState(false);

  if (!steps || steps.length === 0) return null;

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm bg-white mt-4">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-slate-50 hover:bg-slate-100 text-xs text-slate-600 font-medium transition-colors border-b border-transparent data-[state=open]:border-slate-200"
        data-state={open ? "open" : "closed"}
      >
        <span>Agent 推理步骤 ({steps.length})</span>
        {open ? (
          <ChevronDown className="w-4 h-4 text-slate-400" />
        ) : (
          <ChevronRight className="w-4 h-4 text-slate-400" />
        )}
      </button>
      {open && (
        <div className="px-4 py-3 space-y-2 bg-white">
          {steps.map((step, i) => (
            <div key={step.id || i} className="flex items-center gap-2.5 text-xs">
              <span
                className={clsx(
                  "w-1.5 h-1.5 rounded-full flex-shrink-0",
                  step.status === "completed" ? "bg-green-500 shadow-[0_0_4px_rgba(34,197,94,0.5)]" : "bg-amber-400 animate-pulse"
                )}
              />
              <span className="font-mono text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded text-[11px] font-semibold">{step.tool}</span>
              <span className="text-slate-500 truncate">
                {JSON.stringify(step.input).slice(0, 60)}
                {JSON.stringify(step.input).length > 60 ? "..." : ""}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
