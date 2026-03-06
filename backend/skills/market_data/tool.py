"""Market data skill — real-time quotes and historical OHLCV data."""

import logging
import re

import yfinance as yf
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator, model_validator

from services.cache_service import cached

logger = logging.getLogger(__name__)

VALID_INTERVALS = ("1d", "1wk", "1mo")
VALID_PERIODS = ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class GetRealTimeQuoteInput(BaseModel):
    """Schema for get_real_time_quote."""

    ticker: str = Field(description="Stock symbol, e.g. BABA, TSLA, 0700.HK, ^GSPC")

    @field_validator("ticker")
    @classmethod
    def ticker_not_empty(cls, v: str) -> str:
        t = (v or "").strip()
        if not t:
            raise ValueError("ticker must be non-empty")
        return t


class GetHistoricalPricesInput(BaseModel):
    """Schema for get_historical_prices."""

    ticker: str = Field(description="Stock symbol")
    period: str | None = Field(
        default=None,
        description="Time range: 1d/5d/1mo/3mo/6mo/1y/2y/5y/max (mutually exclusive with start/end)",
    )
    start: str | None = Field(
        default=None,
        description="Start date YYYY-MM-DD (use with end, mutually exclusive with period)",
    )
    end: str | None = Field(
        default=None,
        description="End date YYYY-MM-DD (use with start, mutually exclusive with period)",
    )
    interval: str = Field(default="1d", description="Granularity: 1d / 1wk / 1mo")

    @field_validator("ticker")
    @classmethod
    def ticker_not_empty(cls, v: str) -> str:
        t = (v or "").strip()
        if not t:
            raise ValueError("ticker must be non-empty")
        return t

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.period and (self.start or self.end):
            raise ValueError("Parameters 'period' and 'start/end' cannot be used together")
        if (self.start and not self.end) or (self.end and not self.start):
            raise ValueError("Both 'start' and 'end' must be provided together")
        if self.period and self.period not in VALID_PERIODS:
            raise ValueError(f"period must be one of {VALID_PERIODS}")
        if self.interval not in VALID_INTERVALS:
            raise ValueError(f"interval must be one of {VALID_INTERVALS}")
        if self.start and not DATE_PATTERN.match(self.start):
            raise ValueError("start must be YYYY-MM-DD")
        if self.end and not DATE_PATTERN.match(self.end):
            raise ValueError("end must be YYYY-MM-DD")
        return self


@tool(args_schema=GetRealTimeQuoteInput)
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


@tool(args_schema=GetHistoricalPricesInput)
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
    if not period and not start:
        period = "1mo"

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
