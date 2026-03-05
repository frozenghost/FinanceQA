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
    获取股票实时报价和基本信息。
    - ticker: 股票代码，如 BABA、TSLA、0700.HK、^GSPC
    返回当前价格、日内涨跌幅、成交量、52周高低点等实时数据。
    适用于快速查询当前价格、盘中表现等场景。
    """
    logger.info(f"[get_real_time_quote] 开始获取 {ticker} 的实时报价")
    
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        tk = yf.Ticker(ticker)
        info = await loop.run_in_executor(None, lambda: tk.info)

        if not info or "currentPrice" not in info:
            logger.warning(f"[get_real_time_quote] 未找到 {ticker} 的实时报价数据")
            return {"error": f"未找到 {ticker} 的实时报价"}

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
            "data_source": "yfinance",
            "delay_note": "数据约有 15 分钟延迟",
        }
        
        logger.info(f"[get_real_time_quote] 成功获取 {ticker} 报价: ${result['current_price']} ({result['change_percent']:+.2f}%)")
        return result
        
    except Exception as e:
        logger.error(f"[get_real_time_quote] 获取实时报价失败 {ticker}: {e}", exc_info=True)
        return {"error": f"获取实时报价失败: {str(e)}"}


@tool
@cached(key_prefix="ohlcv", ttl=3600)
async def get_historical_prices(
    ticker: str,
    period: Literal["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"] = "1mo",
    interval: Literal["1d", "1wk", "1mo"] = "1d",
) -> dict:
    """
    获取股票历史价格数据（OHLCV）。
    - ticker: 股票代码
    - period: 时间范围，支持 1d/5d/1mo/3mo/6mo/1y/2y/5y/max
    - interval: 数据粒度，支持 1d(日线)/1wk(周线)/1mo(月线)
    返回完整的 OHLCV 数据列表，包含开盘价、最高价、最低价、收盘价、成交量。
    适用于绘制K线图、计算技术指标、分析历史走势等场景。
    """
    logger.info(f"[get_historical_prices] 开始获取 {ticker} 历史数据: period={period}, interval={interval}")
    
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        tk = yf.Ticker(ticker)
        hist = await loop.run_in_executor(None, lambda: tk.history(period=period, interval=interval))

        if hist.empty:
            logger.warning(f"[get_historical_prices] 未找到 {ticker} 的历史数据")
            return {"error": f"未找到 {ticker} 的历史数据"}

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

        # 计算区间统计
        closes = hist["Close"]
        period_return = ((closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0] * 100) if len(closes) > 1 else 0

        result = {
            "ticker": ticker,
            "period": period,
            "interval": interval,
            "data_points": len(ohlcv),
            "period_return_pct": round(float(period_return), 2),
            "period_high": round(float(hist["High"].max()), 2),
            "period_low": round(float(hist["Low"].min()), 2),
            "ohlcv": ohlcv,
            "data_source": "yfinance",
        }
        
        logger.info(f"[get_historical_prices] 成功获取 {ticker} 历史数据: {len(ohlcv)} 个数据点, 区间收益 {period_return:+.2f}%")
        return result
        
    except Exception as e:
        logger.error(f"[get_historical_prices] 获取历史数据失败 {ticker}: {e}", exc_info=True)
        return {"error": f"获取历史数据失败: {str(e)}"}
