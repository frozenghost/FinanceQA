/**
 * MessageRenderer — renders chat messages with Markdown, data cards, and step folding.
 */

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { clsx } from "clsx";
import "katex/dist/katex.min.css";
import {
  User,
  Bot,
  ChevronDown,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Minus,
} from "lucide-react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import type { Message, MessageMetadata } from "../hooks/useSSEChat";
import { PriceChart } from "./PriceChart";

interface Props {
  message: Message;
  isThinking?: boolean;
}

function hasEarningsChartData(metadata: MessageMetadata): boolean {
  const cs = metadata.chart_series;
  if (!cs) return false;
  const q = cs.quarterly?.labels?.length ?? 0;
  const a = cs.annual?.labels?.length ?? 0;
  const e = cs.eps_surprise?.dates?.length ?? 0;
  return q > 0 || a > 0 || e > 0;
}

export function MessageRenderer({ message, isThinking }: Props) {
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
        <div className="w-8 h-8 rounded-full bg-slate-950 text-emerald-300 flex items-center justify-center shrink-0 mt-0.5 shadow-[0_12px_32px_rgba(16,185,129,0.62)] border border-emerald-400/70">
          <Bot className="w-5 h-5" />
        </div>
      )}

      <div
        className={clsx(
          "rounded-2xl px-5 py-3.5 text-sm shadow-[0_16px_40px_rgba(15,23,42,0.9)] border backdrop-blur-2xl",
          isUser
            ? "max-w-[85%] bg-emerald-500/15 text-emerald-100 border-emerald-400/80 rounded-tr-sm"
            : "w-full bg-slate-900/80 text-slate-50 border-slate-700/80 rounded-tl-sm"
        )}
      >
        {/* Coordinator thinking (above answer, expanded by default) */}
        {!isUser && message.metadata?.coordinator && (
          <div className="mb-3">
            <CoordinatorFold coordinator={message.metadata.coordinator} />
          </div>
        )}

        {/* Metadata cards (market, technical — display before content) */}
        {message.metadata && <MetadataCardsTop metadata={message.metadata} />}

        {/* Message content */}
        {message.content && (
          <div
            className={clsx(
              "prose prose-invert prose-sm max-w-none",
              message.metadata && "mt-3"
            )}
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeKatex]}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {/* Inline thinking indicator when assistant is generating */}
        {!isUser && isThinking && (
          <div
            className={clsx(
              "mt-3",
              !message.content && !message.metadata && "mt-0"
            )}
          >
            {!message.content && (
              <div className="text-xs text-slate-300 mb-1">Thinking</div>
            )}
            <div className="flex gap-1.5 items-center text-slate-400 text-xs">
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
                Generating answer...
              </span>
            </div>
          </div>
        )}

        {/* Agent reasoning steps (display after content) */}
        {message.metadata?.steps && message.metadata.steps.length > 0 && (
          <StepsFold steps={message.metadata.steps} />
        )}
      </div>

      {/* User avatar */}
      {isUser && (
        <div className="w-8 h-8 rounded-full bg-slate-950 text-emerald-300 flex items-center justify-center shrink-0 mt-0.5 shadow-[0_12px_32px_rgba(16,185,129,0.62)] border border-emerald-400/70">
          <User className="w-4 h-4" />
        </div>
      )}
    </div>
  );
}

function MetadataCardsTop({ metadata }: { metadata: MessageMetadata }) {
  return (
    <div className="space-y-3">
      {/* Market data card */}
      {(metadata.type === "market" ||
        metadata.type === "hybrid" ||
        (!!metadata.ticker && !!metadata.ohlcv?.length)) && (
        <MarketCard metadata={metadata} />
      )}

      {/* Technical indicators card */}
      {(metadata.type === "technical" ||
        metadata.type === "hybrid" ||
        !!metadata.indicators) && (
        <TechnicalCard metadata={metadata} />
      )}

      {/* Earnings card (quarterly/annual + charts); hide when no data in range */}
      {(metadata.type === "earnings" ||
        (!!metadata.chart_series && !!metadata.ticker)) &&
        !metadata.no_earnings_in_range &&
        hasEarningsChartData(metadata) && (
        <EarningsCard metadata={metadata} />
      )}
    </div>
  );
}

function MarketCard({ metadata }: { metadata: MessageMetadata }) {
  const trendIcon =
    metadata.trend === "up" ? (
      <TrendingUp className="w-4 h-4 text-green-500" />
    ) : metadata.trend === "down" ? (
      <TrendingDown className="w-4 h-4 text-red-500" />
    ) : (
      <Minus className="w-4 h-4 text-yellow-500" />
    );

  const changeColor =
    (metadata.change_pct ?? 0) > 0
      ? "text-emerald-400"
      : (metadata.change_pct ?? 0) < 0
        ? "text-pink-300"
        : "text-slate-400";

  return (
    <div className="bg-slate-950/85 border border-emerald-500/30 rounded-2xl p-4 shadow-[0_18px_45px_rgba(15,23,42,0.95)] w-full">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-mono font-semibold text-slate-50 text-base tracking-tight">
            {metadata.ticker}
          </span>
          {trendIcon}
        </div>
        <span className="text-xl font-bold text-emerald-300">
          ${metadata.current?.toFixed(2)}
        </span>
      </div>
      <div className="flex items-center gap-1.5 bg-slate-900/80 w-fit px-2 py-1 rounded-md border border-slate-700/80">
        <span className={clsx("text-sm font-medium", changeColor)}>
          {(metadata.change_pct ?? 0) > 0 ? "+" : ""}
          {metadata.change_pct?.toFixed(2)}%
        </span>
        <span className="text-xs text-slate-400 font-medium">{metadata.trend}</span>
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
  
  // Flatten nested indicators structure
  const flatIndicators: Record<string, number | null> = {};
  
  Object.entries(indicators).forEach(([category, values]) => {
    if (typeof values === 'object' && values !== null && !Array.isArray(values)) {
      // Nested structure (moving_averages, momentum, trend, volatility)
      Object.entries(values as Record<string, number | null>).forEach(([key, value]) => {
        flatIndicators[key] = value;
      });
    } else {
      // Flat structure (backward compatibility)
      flatIndicators[category] = values as number | null;
    }
  });
  
  return (
    <div className="bg-slate-950/80 border border-slate-700/80 rounded-xl p-4 shadow-[0_18px_45px_rgba(15,23,42,0.95)] backdrop-blur-2xl w-full">
      <div className="text-xs text-slate-300 mb-3 font-semibold uppercase tracking-wider">
        Technical indicators
      </div>
      <div className="grid grid-cols-3 gap-3 text-xs">
        {Object.entries(flatIndicators).map(([key, value]) => (
          <div
            key={key}
            className="bg-slate-900/80 rounded-lg p-2.5 border border-slate-700/80"
          >
            <div className="text-slate-200 font-medium">{key}</div>
            <div className="font-mono font-semibold text-slate-50 mt-1">
              {value !== null && value !== undefined ? value : "N/A"}
            </div>
          </div>
        ))}
      </div>
      {metadata.signals && metadata.signals.length > 0 && (
        <div className="mt-3 space-y-1.5 bg-emerald-500/10 p-2.5 rounded-lg border border-emerald-400/60">
          {metadata.signals.map((signal, i) => (
            <div key={i} className="text-xs text-slate-100 flex items-start gap-1.5">
              <span className="text-emerald-400 mt-0.5">•</span>
              {signal}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function formatMillions(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(2)}K`;
  return value.toFixed(2);
}

function EarningsCard({ metadata }: { metadata: MessageMetadata }) {
  const cs = metadata.chart_series;
  const ticker = metadata.ticker ?? "";

  const quarterlyData =
    cs?.quarterly?.labels?.map((label, i) => ({
      label: label.slice(0, 7),
      revenue: cs.quarterly!.revenue[i] ?? 0,
      earnings: cs.quarterly!.earnings[i] ?? 0,
      profit_margin: cs.quarterly!.profit_margin[i],
      operating_margin: cs.quarterly!.operating_margin[i],
    })) ?? [];

  const epsSurpriseData =
    cs?.eps_surprise?.dates?.map((date, i) => ({
      date: date.slice(0, 7),
      actual: cs.eps_surprise!.eps_actual[i] ?? 0,
      estimate: cs.eps_surprise!.eps_estimate[i] ?? 0,
      surprise: cs.eps_surprise!.surprise_percent[i],
    })) ?? [];

  return (
    <div className="bg-slate-950/85 border border-amber-500/30 rounded-2xl p-4 shadow-[0_18px_45px_rgba(15,23,42,0.95)] w-full">
      <div className="flex items-center gap-2 mb-3">
        <span className="font-mono font-semibold text-slate-50 text-base tracking-tight">
          {ticker}
        </span>
        <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">
          Earnings &amp; Revenue
        </span>
      </div>

      {quarterlyData.length > 0 && (
        <div className="mt-3">
          <div className="text-xs text-amber-300/90 mb-2 font-medium">
            Quarterly Revenue &amp; Net Income
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={quarterlyData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10, fill: "#64748b" }}
                stroke="#1e293b"
                tickLine={false}
                axisLine={false}
                dy={8}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "#64748b" }}
                stroke="#1e293b"
                tickLine={false}
                axisLine={false}
                width={42}
                tickFormatter={(v) => formatMillions(v)}
                dx={-8}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#020617",
                  border: "1px solid #1f2937",
                  borderRadius: "0.5rem",
                  fontSize: "12px",
                  color: "#e5e7eb",
                }}
                formatter={(value: number) => [formatMillions(value), ""]}
                labelFormatter={(label) => `Period ${label}`}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="revenue" fill="#f59e0b" name="Revenue" radius={[2, 2, 0, 0]} />
              <Bar dataKey="earnings" fill="#22c55e" name="Net Income" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {quarterlyData.some((d) => d.profit_margin != null || d.operating_margin != null) && (
        <div className="mt-4">
          <div className="text-xs text-amber-300/90 mb-2 font-medium">
            Margins (%)
          </div>
          <ResponsiveContainer width="100%" height={140}>
            <LineChart data={quarterlyData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10, fill: "#64748b" }}
                stroke="#1e293b"
                tickLine={false}
                axisLine={false}
                dy={8}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "#64748b" }}
                stroke="#1e293b"
                tickLine={false}
                axisLine={false}
                width={36}
                tickFormatter={(v) => `${v}%`}
                domain={[0, "auto"]}
                dx={-8}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#020617",
                  border: "1px solid #1f2937",
                  borderRadius: "0.5rem",
                  fontSize: "12px",
                  color: "#e5e7eb",
                }}
                formatter={(value: unknown) => [typeof value === "number" && !Number.isNaN(value) ? `${value.toFixed(1)}%` : "—", ""]}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line
                type="monotone"
                dataKey="profit_margin"
                stroke="#a78bfa"
                strokeWidth={2}
                dot={{ r: 3 }}
                name="Profit Margin"
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="operating_margin"
                stroke="#38bdf8"
                strokeWidth={2}
                dot={{ r: 3 }}
                name="Operating Margin"
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {epsSurpriseData.length > 0 && (
        <div className="mt-4">
          <div className="text-xs text-amber-300/90 mb-2 font-medium">
            EPS: Actual vs Estimate
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={epsSurpriseData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: "#64748b" }}
                stroke="#1e293b"
                tickLine={false}
                axisLine={false}
                dy={8}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "#64748b" }}
                stroke="#1e293b"
                tickLine={false}
                axisLine={false}
                width={40}
                dx={-8}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#020617",
                  border: "1px solid #1f2937",
                  borderRadius: "0.5rem",
                  fontSize: "12px",
                  color: "#e5e7eb",
                }}
                formatter={(value: number) => [value?.toFixed(2) ?? "—", ""]}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="actual" fill="#22c55e" name="Actual" radius={[2, 2, 0, 0]} />
              <Bar dataKey="estimate" fill="#64748b" name="Estimate" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {quarterlyData.length === 0 && epsSurpriseData.length === 0 && (
        <div className="text-xs text-slate-400 py-2">No chart data available.</div>
      )}
    </div>
  );
}

function StepsFold({ steps }: { steps: MessageMetadata["steps"] }) {
  const [open, setOpen] = useState(false);

  if (!steps || steps.length === 0) return null;

  return (
    <div className="border border-slate-700/80 rounded-xl overflow-hidden shadow-[0_18px_45px_rgba(15,23,42,0.95)] bg-slate-950/80 backdrop-blur-2xl mt-4 w-full">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-slate-900/80 hover:bg-slate-800/80 text-xs text-slate-300 font-medium transition-colors border-b border-transparent data-[state=open]:border-slate-700/70"
        data-state={open ? "open" : "closed"}
      >
        <span>Agent reasoning steps ({steps.length})</span>
        {/* Agent reasoning steps */}
        {open ? (
          <ChevronDown className="w-4 h-4 text-slate-400" />
        ) : (
          <ChevronRight className="w-4 h-4 text-slate-400" />
        )}
      </button>
      {open && (
        <div className="px-4 py-3 space-y-2 bg-slate-950/70">
          {steps.map((step, i) => (
            <div key={step.id || i} className="flex items-center gap-2.5 text-xs">
              <span
                className={clsx(
                  "w-1.5 h-1.5 rounded-full shrink-0",
                  step.status === "completed"
                    ? "bg-green-500 shadow-[0_0_4px_rgba(34,197,94,0.5)]"
                    : "bg-amber-400 animate-pulse"
                )}
              />
              <span className="font-mono text-xs font-semibold px-1.5 py-0.5 rounded border border-pink-500/40 text-pink-300 bg-pink-500/10">
                {step.tool}
              </span>
              <span className="text-slate-300 truncate">
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

function CoordinatorFold({ coordinator }: { coordinator: MessageMetadata["coordinator"] }) {
  const [open, setOpen] = useState(true); // Default to open
  const [hasCollapsed, setHasCollapsed] = useState(false);

  if (!coordinator) return null;

  // Check if we have valid coordinator data
  const hasReasoning = coordinator.reasoning && coordinator.reasoning.trim().length > 0;
  const isComplete = coordinator.isComplete === true;

  if (!hasReasoning) return null;

  // Auto-collapse when thinking is complete
  if (open && !hasCollapsed && isComplete) {
    // Use setTimeout to avoid state update during render
    setTimeout(() => {
      setOpen(false);
      setHasCollapsed(true);
    }, 500); // Small delay to let user see the complete thinking
  }

  return (
    <div className="border border-pink-500/30 rounded-xl overflow-hidden shadow-[0_18px_45px_rgba(236,72,153,0.16)] bg-gradient-to-br from-pink-950/40 to-slate-950/40 backdrop-blur-2xl">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-pink-900/20 hover:bg-pink-800/30 text-xs text-pink-100 font-medium transition-colors border-b border-transparent data-[state=open]:border-pink-500/30"
        data-state={open ? "open" : "closed"}
      >
        <span className="flex items-center gap-2">
          <span className="text-pink-300">🧠</span>
          <span>Coordinator thinking process</span>
          {!isComplete && (
            <span className="text-[10px] text-pink-300/80 animate-pulse">Thinking…</span>
          )}
        </span>
        {open ? (
          <ChevronDown className="w-4 h-4 text-pink-300" />
        ) : (
          <ChevronRight className="w-4 h-4 text-pink-300" />
        )}
      </button>
      {open && (
        <div className="px-4 py-3 bg-slate-950/50">
          {coordinator.analysis_start && coordinator.analysis_end && (
            <div className="text-xs text-slate-400 font-mono mb-3 pb-2 border-b border-slate-700/80">
              Coordinator analysis window: start={coordinator.analysis_start}, end={coordinator.analysis_end}
            </div>
          )}
          <div className="prose prose-invert prose-sm max-w-none prose-headings:text-pink-200 prose-headings:text-xs prose-headings:font-semibold prose-headings:uppercase prose-headings:tracking-wider prose-headings:mb-2 prose-p:text-slate-200 prose-p:text-xs prose-p:leading-relaxed prose-ul:text-slate-200 prose-ul:text-xs prose-li:my-1 prose-strong:text-emerald-400 prose-strong:font-semibold">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
            >
              {coordinator.reasoning}
            </ReactMarkdown>
            {!isComplete && (
              <span className="inline-block w-2 h-4 ml-1 bg-purple-400 animate-pulse align-middle" aria-hidden />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
