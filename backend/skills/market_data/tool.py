"""Market data skill — fetches OHLCV data from Yahoo Finance."""

import yfinance as yf
from langchain_core.tools import tool

from services.cache_service import cached


@tool
@cached(key_prefix="market", ttl=3600)
def get_market_data(ticker: str, period: str = "7d") -> dict:
    """
    获取股票历史行情数据并计算涨跌幅与趋势。
    - ticker: 股票代码，如 BABA、TSLA、0700.HK
    - period: 时间范围，支持 1d / 7d / 30d / 90d / 1y
    返回当前价格、区间涨跌幅、最高/最低价、OHLCV 列表、趋势判断。
    注意：返回数据来自 Yahoo Finance，约有 15 分钟延迟。
    """
    tk = yf.Ticker(ticker)
    hist = tk.history(period=period)

    if hist.empty:
        return {"error": f"未找到 {ticker} 的行情数据，请确认代码正确"}

    current = hist["Close"].iloc[-1]
    if len(hist) >= 2:
        prev_close = hist["Close"].iloc[-2]
        change_pct = (current - prev_close) / prev_close * 100
    else:
        start = hist["Open"].iloc[0]
        change_pct = (current - start) / start * 100
    trend = "上涨" if change_pct > 3 else ("下跌" if change_pct < -3 else "震荡")

    return {
        "ticker": ticker,
        "current": round(float(current), 2),
        "change_pct": round(float(change_pct), 2),
        "high": round(float(hist["High"].max()), 2),
        "low": round(float(hist["Low"].min()), 2),
        "trend": trend,
        "ohlcv": hist[["Open", "High", "Low", "Close", "Volume"]]
        .reset_index()
        .to_dict("records"),
        "data_source": "yfinance",
        "delay_note": "数据约有 15 分钟延迟",
    }
