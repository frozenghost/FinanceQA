"""Technical analysis skill — indicators, patterns, and signals."""

import logging

import pandas as pd
import yfinance as yf
from langchain_core.tools import tool

from services.cache_service import cached

logger = logging.getLogger(__name__)


@tool
@cached(key_prefix="ta", ttl=3600)
async def calculate_technical_indicators(ticker: str, period: str = "6mo") -> dict:
    """
    计算股票的技术指标：移动平均线、RSI、MACD、布林带等。
    - ticker: 股票代码
    - period: 计算周期，建议 3mo/6mo/1y 以获得稳定指标
    返回常用技术指标的当前值和技术信号判断。
    适用于技术分析、买卖信号判断、趋势识别等场景。
    """
    try:
        import asyncio
        import pandas_ta as ta

        loop = asyncio.get_event_loop()
        tk = yf.Ticker(ticker)
        hist = await loop.run_in_executor(None, lambda: tk.history(period=period))

        if hist.empty or len(hist) < 60:
            return {"error": f"数据不足，无法计算技术指标（需要至少60个交易日）"}

        df = hist.copy()

        # 移动平均线
        df["SMA_5"] = ta.sma(df["Close"], length=5)
        df["SMA_20"] = ta.sma(df["Close"], length=20)
        df["SMA_60"] = ta.sma(df["Close"], length=60)
        df["EMA_12"] = ta.ema(df["Close"], length=12)
        df["EMA_26"] = ta.ema(df["Close"], length=26)

        # RSI
        df["RSI_14"] = ta.rsi(df["Close"], length=14)

        # MACD
        macd = ta.macd(df["Close"], fast=12, slow=26, signal=9)
        if macd is not None:
            df = pd.concat([df, macd], axis=1)

        # 布林带
        bbands = ta.bbands(df["Close"], length=20, std=2)
        if bbands is not None:
            df = pd.concat([df, bbands], axis=1)

        # ATR (波动率)
        df["ATR_14"] = ta.atr(df["High"], df["Low"], df["Close"], length=14)

        latest = df.iloc[-1]
        current_price = float(latest["Close"])

        # 生成技术信号
        signals = []
        signal_strength = {"bullish": 0, "bearish": 0}

        # 均线信号
        sma5 = latest.get("SMA_5")
        sma20 = latest.get("SMA_20")
        sma60 = latest.get("SMA_60")
        
        if pd.notna(sma5) and pd.notna(sma20):
            if sma5 > sma20:
                signals.append("短期均线(5日)上穿中期均线(20日)，短期看涨")
                signal_strength["bullish"] += 1
            else:
                signals.append("短期均线(5日)下穿中期均线(20日)，短期看跌")
                signal_strength["bearish"] += 1

        if pd.notna(sma20) and pd.notna(sma60):
            if sma20 > sma60:
                signals.append("中期均线(20日)在长期均线(60日)上方，中期趋势向上")
                signal_strength["bullish"] += 1
            else:
                signals.append("中期均线(20日)在长期均线(60日)下方，中期趋势向下")
                signal_strength["bearish"] += 1

        # RSI 信号
        rsi = latest.get("RSI_14")
        if pd.notna(rsi):
            rsi_val = float(rsi)
            if rsi_val > 70:
                signals.append(f"RSI={rsi_val:.1f}，超买区域，可能回调")
                signal_strength["bearish"] += 1
            elif rsi_val < 30:
                signals.append(f"RSI={rsi_val:.1f}，超卖区域，可能反弹")
                signal_strength["bullish"] += 1
            else:
                signals.append(f"RSI={rsi_val:.1f}，正常区间")

        # MACD 信号
        macd_val = latest.get("MACD_12_26_9")
        macd_signal = latest.get("MACDs_12_26_9")
        macd_hist = latest.get("MACDh_12_26_9")
        
        if pd.notna(macd_val) and pd.notna(macd_signal):
            if float(macd_val) > float(macd_signal):
                signals.append("MACD在信号线上方，动能看涨")
                signal_strength["bullish"] += 1
            else:
                signals.append("MACD在信号线下方，动能看跌")
                signal_strength["bearish"] += 1

        # 布林带信号
        bb_upper = latest.get("BBU_20_2.0")
        bb_lower = latest.get("BBL_20_2.0")
        bb_mid = latest.get("BBM_20_2.0")
        
        if pd.notna(bb_upper) and pd.notna(bb_lower):
            if current_price > float(bb_upper):
                signals.append("价格突破布林带上轨，可能超买")
                signal_strength["bearish"] += 1
            elif current_price < float(bb_lower):
                signals.append("价格跌破布林带下轨，可能超卖")
                signal_strength["bullish"] += 1

        # 综合判断
        if signal_strength["bullish"] > signal_strength["bearish"]:
            overall_signal = "看涨"
        elif signal_strength["bearish"] > signal_strength["bullish"]:
            overall_signal = "看跌"
        else:
            overall_signal = "中性"

        return {
            "ticker": ticker,
            "current_price": round(current_price, 2),
            "indicators": {
                "moving_averages": {
                    "SMA_5": round(float(sma5), 2) if pd.notna(sma5) else None,
                    "SMA_20": round(float(sma20), 2) if pd.notna(sma20) else None,
                    "SMA_60": round(float(sma60), 2) if pd.notna(sma60) else None,
                    "EMA_12": round(float(latest.get("EMA_12")), 2) if pd.notna(latest.get("EMA_12")) else None,
                    "EMA_26": round(float(latest.get("EMA_26")), 2) if pd.notna(latest.get("EMA_26")) else None,
                },
                "momentum": {
                    "RSI_14": round(float(rsi), 2) if pd.notna(rsi) else None,
                },
                "trend": {
                    "MACD": round(float(macd_val), 4) if pd.notna(macd_val) else None,
                    "MACD_signal": round(float(macd_signal), 4) if pd.notna(macd_signal) else None,
                    "MACD_histogram": round(float(macd_hist), 4) if pd.notna(macd_hist) else None,
                },
                "volatility": {
                    "BB_upper": round(float(bb_upper), 2) if pd.notna(bb_upper) else None,
                    "BB_middle": round(float(bb_mid), 2) if pd.notna(bb_mid) else None,
                    "BB_lower": round(float(bb_lower), 2) if pd.notna(bb_lower) else None,
                    "ATR_14": round(float(latest.get("ATR_14")), 2) if pd.notna(latest.get("ATR_14")) else None,
                },
            },
            "signals": signals,
            "overall_signal": overall_signal,
            "signal_strength": signal_strength,
            "data_source": "yfinance + pandas-ta",
            "disclaimer": "技术指标仅供参考，不构成投资建议",
        }
    
    except Exception as e:
        logger.error(f"技术指标计算失败 {ticker}: {e}")
        return {"error": f"技术指标计算失败: {str(e)}"}
