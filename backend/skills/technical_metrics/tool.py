"""Technical metrics skill — computes MA, RSI, MACD via pandas-ta."""

import logging

import pandas as pd
import yfinance as yf
from langchain_core.tools import tool

from services.cache_service import cached

logger = logging.getLogger(__name__)


@tool
@cached(key_prefix="ta", ttl=3600)
def get_technical_indicators(ticker: str, period: str = "90d") -> dict:
    """
    计算股票的常用技术指标：移动平均线(MA)、RSI、MACD。
    - ticker: 股票代码，如 BABA、TSLA、0700.HK
    - period: 时间范围，建议 90d 或更长以获得更稳定的指标
    返回 MA5/MA20/MA60、RSI(14)、MACD 信号线，以及综合技术判断。
    适用于用户询问技术分析、买卖信号、超买超卖等问题。
    """
    try:
        import pandas_ta as ta

        tk = yf.Ticker(ticker)
        hist = tk.history(period=period)

        if hist.empty:
            return {"error": f"未找到 {ticker} 的行情数据"}

        df = hist.copy()

        # Moving Averages
        df["MA5"] = ta.sma(df["Close"], length=5)
        df["MA20"] = ta.sma(df["Close"], length=20)
        df["MA60"] = ta.sma(df["Close"], length=60)

        # RSI (14-period)
        df["RSI"] = ta.rsi(df["Close"], length=14)

        # MACD
        macd = ta.macd(df["Close"])
        if macd is not None:
            df = pd.concat([df, macd], axis=1)

        latest = df.iloc[-1]
        current_price = float(latest["Close"])

        # Technical signals
        signals = []

        # MA signals
        ma5 = latest.get("MA5")
        ma20 = latest.get("MA20")
        if pd.notna(ma5) and pd.notna(ma20):
            if ma5 > ma20:
                signals.append("短期均线在长期均线上方，短期趋势向上")
            else:
                signals.append("短期均线在长期均线下方，短期趋势向下")

        # RSI signal
        rsi = latest.get("RSI")
        if pd.notna(rsi):
            rsi_val = float(rsi)
            if rsi_val > 70:
                signals.append(f"RSI={rsi_val:.1f}，处于超买区域")
            elif rsi_val < 30:
                signals.append(f"RSI={rsi_val:.1f}，处于超卖区域")
            else:
                signals.append(f"RSI={rsi_val:.1f}，处于正常区间")

        # MACD signal
        macd_val = latest.get("MACD_12_26_9")
        macd_signal = latest.get("MACDs_12_26_9")
        if pd.notna(macd_val) and pd.notna(macd_signal):
            if float(macd_val) > float(macd_signal):
                signals.append("MACD 在信号线上方，可能为看涨信号")
            else:
                signals.append("MACD 在信号线下方，可能为看跌信号")

        return {
            "ticker": ticker,
            "current_price": round(current_price, 2),
            "indicators": {
                "MA5": round(float(ma5), 2) if pd.notna(ma5) else None,
                "MA20": round(float(ma20), 2) if pd.notna(ma20) else None,
                "MA60": round(float(latest.get("MA60", float("nan"))), 2)
                if pd.notna(latest.get("MA60"))
                else None,
                "RSI_14": round(float(rsi), 2) if pd.notna(rsi) else None,
                "MACD": round(float(macd_val), 4) if pd.notna(macd_val) else None,
                "MACD_signal": round(float(macd_signal), 4)
                if pd.notna(macd_signal)
                else None,
            },
            "signals": signals,
            "data_source": "yfinance + pandas-ta",
            "disclaimer": "技术指标仅供参考，不构成投资建议",
        }
    except Exception as e:
        logger.error(f"技术指标计算失败: {e}")
        return {"error": f"技术指标计算失败: {str(e)}"}
