"""Technical analysis skill — indicators, patterns, and signals."""

import logging

import pandas as pd
import yfinance as yf
from langchain_core.tools import tool

from services.cache_service import cached

logger = logging.getLogger(__name__)


@tool
@cached(key_prefix="ta", ttl=3600)
async def calculate_technical_indicators(
    ticker: str,
    start: str,
    end: str,
    interval: str = "1d"
) -> dict:
    """
    Calculate technical indicators for a stock: moving averages, RSI, MACD, Bollinger Bands, etc.
    - ticker: Stock symbol
    - start: Start date, format YYYY-MM-DD (required)
    - end: End date, format YYYY-MM-DD (required)
    - interval: Data granularity, supports 1d / 1wk / 1mo (default 1d)
    Returns current values of common indicators and derived trading signals.
    Useful for technical analysis, signal generation, and trend identification.
    
    Note: enough data points are required:
    - Daily data: at least 20 trading days (~1 month)
    - Weekly data: at least 20 weeks (~5 months)
    - Monthly data: at least 20 months (~2 years)
    
    Examples:
    - calculate_technical_indicators("AAPL", start="2024-01-01", end="2024-03-31")  # Q1 data
    - calculate_technical_indicators("AAPL", start="2023-01-01", end="2024-01-01")  # 1 year of data
    """
    try:
        import asyncio
        import pandas_ta as ta

        time_range = f"start={start}, end={end}"
        logger.info(
            f"[calculate_technical_indicators] Start calculating indicators for {ticker}: "
            f"start={start}, end={end}, interval={interval}"
        )

        loop = asyncio.get_event_loop()
        tk = yf.Ticker(ticker)
        
        # Fetch historical data
        hist = await loop.run_in_executor(None, lambda: tk.history(start=start, end=end, interval=interval))

        if hist.empty:
            return {"error": f"No historical data found for {ticker}"}

        data_points = len(hist)
        
        # Adjust indicator parameters dynamically based on data size
        if data_points < 20:
            return {
                "error": (
                    "Not enough data to compute technical indicators "
                    f"(need at least 20 points, got {data_points}). Consider expanding the time range."
                )
            }
        
        df = hist.copy()

        # Dynamically derive indicator parameters (avoid exceeding available points)
        # Moving averages: use fractions of data length
        sma_short = min(5, max(3, data_points // 12))  # short-term MA: ~1/12 of data
        sma_mid = min(20, max(5, data_points // 3))    # mid-term MA: ~1/3 of data
        sma_long = min(60, max(10, data_points * 2 // 3))  # long-term MA: ~2/3 of data
        
        ema_fast = min(12, max(5, data_points // 5))
        ema_slow = min(26, max(10, data_points // 2))
        
        rsi_period = min(14, max(7, data_points // 4))
        atr_period = min(14, max(7, data_points // 4))
        bb_period = min(20, max(10, data_points // 3))

        # Moving averages
        df["SMA_short"] = ta.sma(df["Close"], length=sma_short)
        df["SMA_mid"] = ta.sma(df["Close"], length=sma_mid)
        df["SMA_long"] = ta.sma(df["Close"], length=sma_long)
        df["EMA_fast"] = ta.ema(df["Close"], length=ema_fast)
        df["EMA_slow"] = ta.ema(df["Close"], length=ema_slow)

        # RSI
        df["RSI"] = ta.rsi(df["Close"], length=rsi_period)

        # MACD (only calculate when enough data)
        if data_points >= 35:
            macd = ta.macd(df["Close"], fast=ema_fast, slow=ema_slow, signal=9)
            if macd is not None:
                df = pd.concat([df, macd], axis=1)

        # Bollinger Bands
        bbands = ta.bbands(df["Close"], length=bb_period, std=2)
        if bbands is not None:
            df = pd.concat([df, bbands], axis=1)

        # ATR (Volatility)
        df["ATR"] = ta.atr(df["High"], df["Low"], df["Close"], length=atr_period)

        latest = df.iloc[-1]
        current_price = float(latest["Close"])

        # Generate signals
        signals = []
        signal_strength = {"bullish": 0, "bearish": 0}

        # Moving-average signals
        sma_short_val = latest.get("SMA_short")
        sma_mid_val = latest.get("SMA_mid")
        sma_long_val = latest.get("SMA_long")
        
        if pd.notna(sma_short_val) and pd.notna(sma_mid_val):
            if sma_short_val > sma_mid_val:
                signals.append(
                    f"Short-term MA ({sma_short}) crossing above mid-term MA ({sma_mid}) — short-term bullish."
                )
                signal_strength["bullish"] += 1
            else:
                signals.append(
                    f"Short-term MA ({sma_short}) crossing below mid-term MA ({sma_mid}) — short-term bearish."
                )
                signal_strength["bearish"] += 1

        if pd.notna(sma_mid_val) and pd.notna(sma_long_val):
            if sma_mid_val > sma_long_val:
                signals.append(
                    f"Mid-term MA ({sma_mid}) above long-term MA ({sma_long}) — medium-term uptrend."
                )
                signal_strength["bullish"] += 1
            else:
                signals.append(
                    f"Mid-term MA ({sma_mid}) below long-term MA ({sma_long}) — medium-term downtrend."
                )
                signal_strength["bearish"] += 1

        # RSI signal
        rsi = latest.get("RSI")
        if pd.notna(rsi):
            rsi_val = float(rsi)
            if rsi_val > 70:
                signals.append(
                    f"RSI({rsi_period})={rsi_val:.1f} — overbought zone, pullback risk."
                )
                signal_strength["bearish"] += 1
            elif rsi_val < 30:
                signals.append(
                    f"RSI({rsi_period})={rsi_val:.1f} — oversold zone, rebound potential."
                )
                signal_strength["bullish"] += 1
            else:
                signals.append(f"RSI({rsi_period})={rsi_val:.1f} — neutral range.")

        # MACD signal
        macd_col = f"MACD_{ema_fast}_{ema_slow}_9"
        macd_signal_col = f"MACDs_{ema_fast}_{ema_slow}_9"
        macd_hist_col = f"MACDh_{ema_fast}_{ema_slow}_9"
        
        macd_val = latest.get(macd_col)
        macd_signal = latest.get(macd_signal_col)
        macd_hist = latest.get(macd_hist_col)
        
        if pd.notna(macd_val) and pd.notna(macd_signal):
            if float(macd_val) > float(macd_signal):
                signals.append("MACD above signal line — bullish momentum.")
                signal_strength["bullish"] += 1
            else:
                signals.append("MACD below signal line — bearish momentum.")
                signal_strength["bearish"] += 1

        # Bollinger Band signal
        bb_upper_col = f"BBU_{bb_period}_2.0"
        bb_lower_col = f"BBL_{bb_period}_2.0"
        bb_mid_col = f"BBM_{bb_period}_2.0"
        
        bb_upper = latest.get(bb_upper_col)
        bb_lower = latest.get(bb_lower_col)
        bb_mid = latest.get(bb_mid_col)
        
        if pd.notna(bb_upper) and pd.notna(bb_lower):
            if current_price > float(bb_upper):
                signals.append("Price broke above Bollinger upper band — potential overbought.")
                signal_strength["bearish"] += 1
            elif current_price < float(bb_lower):
                signals.append("Price broke below Bollinger lower band — potential oversold.")
                signal_strength["bullish"] += 1

        # Overall signal
        if signal_strength["bullish"] > signal_strength["bearish"]:
            overall_signal = "bullish"
        elif signal_strength["bearish"] > signal_strength["bullish"]:
            overall_signal = "bearish"
        else:
            overall_signal = "neutral"

        return {
            "ticker": ticker,
            "time_range": time_range,
            "interval": interval,
            "data_points": data_points,
            "current_price": round(current_price, 2),
            "indicator_periods": {
                "sma_short": sma_short,
                "sma_mid": sma_mid,
                "sma_long": sma_long,
                "ema_fast": ema_fast,
                "ema_slow": ema_slow,
                "rsi": rsi_period,
                "bb": bb_period,
                "atr": atr_period,
            },
            "indicators": {
                "moving_averages": {
                    f"SMA_{sma_short}": round(float(sma_short_val), 2) if pd.notna(sma_short_val) else None,
                    f"SMA_{sma_mid}": round(float(sma_mid_val), 2) if pd.notna(sma_mid_val) else None,
                    f"SMA_{sma_long}": round(float(sma_long_val), 2) if pd.notna(sma_long_val) else None,
                    f"EMA_{ema_fast}": round(float(latest.get("EMA_fast")), 2) if pd.notna(latest.get("EMA_fast")) else None,
                    f"EMA_{ema_slow}": round(float(latest.get("EMA_slow")), 2) if pd.notna(latest.get("EMA_slow")) else None,
                },
                "momentum": {
                    f"RSI_{rsi_period}": round(float(rsi), 2) if pd.notna(rsi) else None,
                },
                "trend": {
                    "MACD": round(float(macd_val), 4) if pd.notna(macd_val) else None,
                    "MACD_signal": round(float(macd_signal), 4) if pd.notna(macd_signal) else None,
                    "MACD_histogram": round(float(macd_hist), 4) if pd.notna(macd_hist) else None,
                },
                "volatility": {
                    f"BB_upper_{bb_period}": round(float(bb_upper), 2) if pd.notna(bb_upper) else None,
                    f"BB_middle_{bb_period}": round(float(bb_mid), 2) if pd.notna(bb_mid) else None,
                    f"BB_lower_{bb_period}": round(float(bb_lower), 2) if pd.notna(bb_lower) else None,
                    f"ATR_{atr_period}": round(float(latest.get("ATR")), 2) if pd.notna(latest.get("ATR")) else None,
                },
            },
            "signals": signals,
            "overall_signal": overall_signal,
            "signal_strength": signal_strength,
            "data_source": "market_data_service",
            "disclaimer": "Technical indicators are for reference only and do not constitute investment advice.",
        }
    
    except Exception as e:
        logger.error(f"Failed to calculate technical indicators for {ticker}: {e}")
        return {"error": f"Failed to calculate technical indicators: {str(e)}"}
