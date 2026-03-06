/**
 * PriceChart — Recharts line chart for OHLCV data.
 */

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

interface OHLCV {
  Date: string;
  Open: number;
  High: number;
  Low: number;
  Close: number;
  Volume: number;
}

interface Props {
  data: OHLCV[];
  ticker: string;
}

export function PriceChart({ data, ticker }: Props) {
  // Format data for Recharts
  const chartData = data.map((d) => ({
    date: formatDate(d.Date),
    close: d.Close,
    high: d.High,
    low: d.Low,
    volume: d.Volume,
  }));

  const prices = chartData.map((d) => d.close);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const padding = (maxPrice - minPrice) * 0.1 || 1;

  return (
    <div className="w-full">
      <div className="text-xs text-emerald-300 mb-2 font-medium bg-slate-950/80 px-2 py-1 rounded-md w-fit border border-emerald-500/40 shadow-[0_10px_28px_rgba(15,23,42,0.9)]">
        {ticker} Price Chart
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#1e293b"
            tickLine={false}
            axisLine={false}
            dy={10}
          />
          <YAxis
            domain={[minPrice - padding, maxPrice + padding]}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#1e293b"
            tickLine={false}
            axisLine={false}
            width={45}
            tickFormatter={(v: number) => v.toFixed(1)}
            dx={-10}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#020617",
              border: "1px solid #1f2937",
              borderRadius: "0.5rem",
              fontSize: "12px",
              color: "#e5e7eb",
              boxShadow:
                "0 18px 45px rgba(15,23,42,0.95)"
            }}
            labelStyle={{ color: "#9ca3af", fontWeight: 500, marginBottom: "4px" }}
            formatter={(value: number) => [`$${value.toFixed(2)}`, "Close"]}
          />
          <Line
            type="monotone"
            dataKey="close"
            stroke="#22c55e"
            strokeWidth={2.5}
            dot={false}
            activeDot={{
              r: 4,
              stroke: "#22c55e",
              strokeWidth: 2,
              fill: "#020617",
            }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return `${(d.getMonth() + 1).toString().padStart(2, "0")}/${d
      .getDate()
      .toString()
      .padStart(2, "0")}`;
  } catch {
    return dateStr.slice(5, 10);
  }
}
