/**
 * Market data hook powered by TanStack Query.
 * Fetches OHLCV data from the backend /api/market/{ticker} endpoint.
 */

import { useQuery } from "@tanstack/react-query";

export interface OHLCV {
  Date: string;
  Open: number;
  High: number;
  Low: number;
  Close: number;
  Volume: number;
}

export interface MarketData {
  ticker: string;
  current: number;
  change_pct: number;
  high: number;
  low: number;
  trend: "上涨" | "下跌" | "震荡";
  ohlcv: OHLCV[];
  data_source: string;
  delay_note: string;
}

export function useMarketData(ticker: string, period = "7d") {
  return useQuery<MarketData>({
    queryKey: ["market", ticker, period],
    queryFn: async () => {
      const res = await fetch(`/api/market/${ticker}?period=${period}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    staleTime: 60_000, // 1 min — matches backend Redis cache TTL
    enabled: !!ticker,
  });
}
