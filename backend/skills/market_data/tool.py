"""Market data skill — real-time quotes and historical OHLCV data."""

import logging
from typing import Literal

import yfinance as yf
from langchain_core.tools import tool

from services.cache_service import cached

logger = logging.getLogger(__name__)


@tool
@cached(key_prefix="quote", ttl=60)
async def get_real_time_quote(ticker: str) -> dict:
    """
    Fetch real-time stock quote and basic information.
    - ticker: Stock symbol, e.g. BABA, TSLA, 0700.HK, ^GSPC
    Returns current price, intraday performance, volume, 52‑week high/low and other real-time fields.
    Suitable for quick checks of current price and intraday performance.
    """
    logger.info(f"[get_real_time_quote] Start fetching real-time quote for {ticker}")
    
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        tk = yf.Ticker(ticker)
        info = await loop.run_in_executor(None, lambda: tk.info)

        if not info or "currentPrice" not in info:
            logger.warning(f"[get_real_time_quote] No real-time quote data found for {ticker}")
            return {"error": f"Real-time quote not found for {ticker}"}

        current = info.get("currentPrice") or info.get("regularMarketPrice")
        prev_close = info.get("previousClose")
        change_pct = ((current - prev_close) / prev_close * 100) if prev_close else 0

        result = {
            "ticker": ticker,
            "name": info.get("longName", info.get("shortName", ticker)),
            "current_price": round(float(current), 2),
            "previous_close": round(float(prev_close), 2) if prev_close else None,
            "change_percent": round(float(change_pct), 2),
            "day_high": info.get("dayHigh"),
            "day_low": info.get("dayLow"),
            "volume": info.get("volume"),
            "market_cap": info.get("marketCap"),
            "52_week_high": info.get("fiftyTwoWeekHigh"),
            "52_week_low": info.get("fiftyTwoWeekLow"),
            "currency": info.get("currency", "USD"),
            "exchange": info.get("exchange"),
            "data_source": "market_data_service",
            "delay_note": "Quotes may be delayed by up to ~15 minutes.",
        }
        
        logger.info(
            f"[get_real_time_quote] Successfully fetched quote for {ticker}: "
            f"${result['current_price']} ({result['change_percent']:+.2f}%)"
        )
        return result
        
    except Exception as e:
        logger.error(f"[get_real_time_quote] Failed to fetch real-time quote for {ticker}: {e}", exc_info=True)
        return {"error": f"Failed to fetch real-time quote: {str(e)}"}


@tool
@cached(key_prefix="ohlcv", ttl=3600)
async def get_historical_prices(
    ticker: str,
    period: str | None = None,
    start: str | None = None,
    end: str | None = None,
    interval: str = "1d",
) -> dict:
    """
    Fetch historical OHLCV price data.
    - ticker: Stock symbol
    - period: Time range, supports 1d/5d/1mo/3mo/6mo/1y/2y/5y/max (mutually exclusive with start/end)
    - start: Start date, format YYYY-MM-DD (mutually exclusive with period, must be used with end)
    - end: End date, format YYYY-MM-DD (mutually exclusive with period, must be used with start)
    - interval: Data granularity, supports 1d (daily) / 1wk (weekly) / 1mo (monthly)
    Returns a full OHLCV list with open, high, low, close, volume.
    Suitable for candlestick charts, technical indicators, and historical analysis.
    
    Examples:
    - get_historical_prices("AAPL", period="1mo")  # last 1 month
    - get_historical_prices("AAPL", start="2024-03-15", end="2024-03-21")  # explicit date range
    """
    # Parameter validation
    if period and (start or end):
        return {"error": "Parameters 'period' and 'start/end' cannot be used together; choose one mode."}
    
    if (start and not end) or (end and not start):
        return {"error": "Both 'start' and 'end' must be provided together."}
    
    if not period and not start:
        period = "1mo"  # default
    
    if period:
        time_range = f"period={period}"
        logger.info(f"[get_historical_prices] Fetching historical data for {ticker}: period={period}, interval={interval}")
    else:
        time_range = f"start={start}, end={end}"
        logger.info(
            f"[get_historical_prices] Fetching historical data for {ticker}: "
            f"start={start}, end={end}, interval={interval}"
        )
    
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        tk = yf.Ticker(ticker)
        
        # Fetch history based on the chosen parameter mode
        if period:
            hist = await loop.run_in_executor(None, lambda: tk.history(period=period, interval=interval))
        else:
            hist = await loop.run_in_executor(None, lambda: tk.history(start=start, end=end, interval=interval))

        if hist.empty:
            logger.warning(f"[get_historical_prices] No historical data found for {ticker}")
            return {"error": f"No historical data found for {ticker}"}

        ohlcv = []
        for idx, row in hist.iterrows():
            ohlcv.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })

        # Basic period statistics
        closes = hist["Close"]
        period_return = ((closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0] * 100) if len(closes) > 1 else 0

        result = {
            "ticker": ticker,
            "time_range": time_range,
            "interval": interval,
            "data_points": len(ohlcv),
            "period_return_pct": round(float(period_return), 2),
            "period_high": round(float(hist["High"].max()), 2),
            "period_low": round(float(hist["Low"].min()), 2),
            "ohlcv": ohlcv,
            "data_source": "market_data_service",
        }
        
        logger.info(
            f"[get_historical_prices] Successfully fetched history for {ticker}: "
            f"{len(ohlcv)} points, period return {period_return:+.2f}%"
        )
        return result
        
    except Exception as e:
        logger.error(f"[get_historical_prices] Failed to fetch history for {ticker}: {e}", exc_info=True)
        return {"error": f"Failed to fetch historical data: {str(e)}"}
