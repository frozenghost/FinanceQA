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
      <div className="text-xs text-slate-500 mb-2 font-medium bg-slate-50 px-2 py-1 rounded-md w-fit border border-slate-100">{ticker} 走势图</div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "#94a3b8" }}
            stroke="#f1f5f9"
            tickLine={false}
            axisLine={false}
            dy={10}
          />
          <YAxis
            domain={[minPrice - padding, maxPrice + padding]}
            tick={{ fontSize: 10, fill: "#94a3b8" }}
            stroke="#f1f5f9"
            tickLine={false}
            axisLine={false}
            width={45}
            tickFormatter={(v: number) => v.toFixed(1)}
            dx={-10}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#ffffff",
              border: "1px solid #e2e8f0",
              borderRadius: "0.5rem",
              fontSize: "12px",
              color: "#334155",
              boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)"
            }}
            labelStyle={{ color: "#64748b", fontWeight: 500, marginBottom: "4px" }}
            formatter={(value: number) => [`$${value.toFixed(2)}`, "收盘价"]}
          />
          <Line
            type="monotone"
            dataKey="close"
            stroke="#3b82f6"
            strokeWidth={2.5}
            dot={false}
            activeDot={{ r: 4, stroke: "#3b82f6", strokeWidth: 2, fill: "#ffffff" }}
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
