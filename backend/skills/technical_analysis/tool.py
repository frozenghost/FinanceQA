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
    计算股票的技术指标：移动平均线、RSI、MACD、布林带等。
    - ticker: 股票代码
    - start: 开始日期，格式 YYYY-MM-DD（必需）
    - end: 结束日期，格式 YYYY-MM-DD（必需）
    - interval: 数据粒度，支持 1d(日线)/1wk(周线)/1mo(月线)（默认 1d）
    返回常用技术指标的当前值和技术信号判断。
    适用于技术分析、买卖信号判断、趋势识别等场景。
    
    注意：计算技术指标需要足够的数据点，建议：
    - 日线数据：至少 20 个交易日（约 1 个月）
    - 周线数据：至少 20 周（约 5 个月）
    - 月线数据：至少 20 个月（约 2 年）
    
    示例：
    - calculate_technical_indicators("AAPL", start="2024-01-01", end="2024-03-31")  # Q1 数据
    - calculate_technical_indicators("AAPL", start="2023-01-01", end="2024-01-01")  # 1 年数据
    """
    try:
        import asyncio
        import pandas_ta as ta

        time_range = f"start={start}, end={end}"
        logger.info(f"[calculate_technical_indicators] 开始计算 {ticker} 技术指标: start={start}, end={end}, interval={interval}")

        loop = asyncio.get_event_loop()
        tk = yf.Ticker(ticker)
        
        # 获取历史数据
        hist = await loop.run_in_executor(None, lambda: tk.history(start=start, end=end, interval=interval))

        if hist.empty:
            return {"error": f"未找到 {ticker} 的历史数据"}

        data_points = len(hist)
        
        # 根据数据点数量动态调整指标参数
        if data_points < 20:
            return {"error": f"数据不足，无法计算技术指标（需要至少20个数据点，当前仅 {data_points} 个）。建议扩大时间范围。"}
        
        df = hist.copy()

        # 动态计算指标参数（确保不超过可用数据点）
        # 移动平均线：使用数据点的比例
        sma_short = min(5, max(3, data_points // 12))  # 短期均线：约1/12数据
        sma_mid = min(20, max(5, data_points // 3))    # 中期均线：约1/3数据
        sma_long = min(60, max(10, data_points * 2 // 3))  # 长期均线：约2/3数据
        
        ema_fast = min(12, max(5, data_points // 5))
        ema_slow = min(26, max(10, data_points // 2))
        
        rsi_period = min(14, max(7, data_points // 4))
        atr_period = min(14, max(7, data_points // 4))
        bb_period = min(20, max(10, data_points // 3))

        # 移动平均线
        df["SMA_short"] = ta.sma(df["Close"], length=sma_short)
        df["SMA_mid"] = ta.sma(df["Close"], length=sma_mid)
        df["SMA_long"] = ta.sma(df["Close"], length=sma_long)
        df["EMA_fast"] = ta.ema(df["Close"], length=ema_fast)
        df["EMA_slow"] = ta.ema(df["Close"], length=ema_slow)

        # RSI
        df["RSI"] = ta.rsi(df["Close"], length=rsi_period)

        # MACD (只在数据足够时计算)
        if data_points >= 35:
            macd = ta.macd(df["Close"], fast=ema_fast, slow=ema_slow, signal=9)
            if macd is not None:
                df = pd.concat([df, macd], axis=1)

        # 布林带
        bbands = ta.bbands(df["Close"], length=bb_period, std=2)
        if bbands is not None:
            df = pd.concat([df, bbands], axis=1)

        # ATR (波动率)
        df["ATR"] = ta.atr(df["High"], df["Low"], df["Close"], length=atr_period)

        latest = df.iloc[-1]
        current_price = float(latest["Close"])

        # 生成技术信号
        signals = []
        signal_strength = {"bullish": 0, "bearish": 0}

        # 均线信号
        sma_short_val = latest.get("SMA_short")
        sma_mid_val = latest.get("SMA_mid")
        sma_long_val = latest.get("SMA_long")
        
        if pd.notna(sma_short_val) and pd.notna(sma_mid_val):
            if sma_short_val > sma_mid_val:
                signals.append(f"短期均线({sma_short}日)上穿中期均线({sma_mid}日)，短期看涨")
                signal_strength["bullish"] += 1
            else:
                signals.append(f"短期均线({sma_short}日)下穿中期均线({sma_mid}日)，短期看跌")
                signal_strength["bearish"] += 1

        if pd.notna(sma_mid_val) and pd.notna(sma_long_val):
            if sma_mid_val > sma_long_val:
                signals.append(f"中期均线({sma_mid}日)在长期均线({sma_long}日)上方，中期趋势向上")
                signal_strength["bullish"] += 1
            else:
                signals.append(f"中期均线({sma_mid}日)在长期均线({sma_long}日)下方，中期趋势向下")
                signal_strength["bearish"] += 1

        # RSI 信号
        rsi = latest.get("RSI")
        if pd.notna(rsi):
            rsi_val = float(rsi)
            if rsi_val > 70:
                signals.append(f"RSI({rsi_period})={rsi_val:.1f}，超买区域，可能回调")
                signal_strength["bearish"] += 1
            elif rsi_val < 30:
                signals.append(f"RSI({rsi_period})={rsi_val:.1f}，超卖区域，可能反弹")
                signal_strength["bullish"] += 1
            else:
                signals.append(f"RSI({rsi_period})={rsi_val:.1f}，正常区间")

        # MACD 信号
        macd_col = f"MACD_{ema_fast}_{ema_slow}_9"
        macd_signal_col = f"MACDs_{ema_fast}_{ema_slow}_9"
        macd_hist_col = f"MACDh_{ema_fast}_{ema_slow}_9"
        
        macd_val = latest.get(macd_col)
        macd_signal = latest.get(macd_signal_col)
        macd_hist = latest.get(macd_hist_col)
        
        if pd.notna(macd_val) and pd.notna(macd_signal):
            if float(macd_val) > float(macd_signal):
                signals.append("MACD在信号线上方，动能看涨")
                signal_strength["bullish"] += 1
            else:
                signals.append("MACD在信号线下方，动能看跌")
                signal_strength["bearish"] += 1

        # 布林带信号
        bb_upper_col = f"BBU_{bb_period}_2.0"
        bb_lower_col = f"BBL_{bb_period}_2.0"
        bb_mid_col = f"BBM_{bb_period}_2.0"
        
        bb_upper = latest.get(bb_upper_col)
        bb_lower = latest.get(bb_lower_col)
        bb_mid = latest.get(bb_mid_col)
        
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
            "data_source": "市场数据服务",
            "disclaimer": "技术指标仅供参考，不构成投资建议",
        }
    
    except Exception as e:
        logger.error(f"技术指标计算失败 {ticker}: {e}")
        return {"error": f"技术指标计算失败: {str(e)}"}
