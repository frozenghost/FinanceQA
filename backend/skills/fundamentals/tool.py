"""Fundamentals skill — company financials, valuation metrics, and earnings data."""

import logging

import pandas as pd
import yfinance as yf
from langchain_core.tools import tool

from services.cache_service import cached

logger = logging.getLogger(__name__)


@tool
@cached(key_prefix="fundamentals", ttl=86400)
async def get_company_fundamentals(ticker: str) -> dict:
    """
    获取公司基本面数据和财务指标。
    - ticker: 股票代码
    返回市盈率、市净率、ROE、利润率、EPS、营收等关键财务指标。
    适用于基本面分析、估值评估、财务健康度判断等场景。
    """
    logger.info(f"[get_company_fundamentals] 开始获取 {ticker} 的基本面数据")
    
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        tk = yf.Ticker(ticker)
        info = await loop.run_in_executor(None, lambda: tk.info)

        if not info:
            logger.warning(f"[get_company_fundamentals] 未找到 {ticker} 的基本面数据")
            return {"error": f"未找到 {ticker} 的基本面数据"}

        result = {
            "ticker": ticker,
            "company_name": info.get("longName", info.get("shortName")),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "valuation": {
                "market_cap": info.get("marketCap"),
                "enterprise_value": info.get("enterpriseValue"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "peg_ratio": info.get("pegRatio"),
                "price_to_book": info.get("priceToBook"),
                "price_to_sales": info.get("priceToSalesTrailing12Months"),
                "ev_to_revenue": info.get("enterpriseToRevenue"),
                "ev_to_ebitda": info.get("enterpriseToEbitda"),
            },
            "profitability": {
                "profit_margin": info.get("profitMargins"),
                "operating_margin": info.get("operatingMargins"),
                "gross_margin": info.get("grossMargins"),
                "roe": info.get("returnOnEquity"),
                "roa": info.get("returnOnAssets"),
            },
            "per_share": {
                "eps_trailing": info.get("trailingEps"),
                "eps_forward": info.get("forwardEps"),
                "book_value": info.get("bookValue"),
                "revenue_per_share": info.get("revenuePerShare"),
            },
            "financial_health": {
                "total_cash": info.get("totalCash"),
                "total_debt": info.get("totalDebt"),
                "debt_to_equity": info.get("debtToEquity"),
                "current_ratio": info.get("currentRatio"),
                "quick_ratio": info.get("quickRatio"),
            },
            "growth": {
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
            },
            "dividend": {
                "dividend_rate": info.get("dividendRate"),
                "dividend_yield": info.get("dividendYield"),
                "payout_ratio": info.get("payoutRatio"),
            },
            "data_source": "财务数据服务",
            "disclaimer": "数据来自公开财报，仅供参考",
        }
        
        logger.info(f"[get_company_fundamentals] 成功获取 {ticker} 基本面: PE={result['valuation']['pe_ratio']}, ROE={result['profitability']['roe']}")
        return result
        
    except Exception as e:
        logger.error(f"[get_company_fundamentals] 获取基本面数据失败 {ticker}: {e}", exc_info=True)
        return {"error": f"获取基本面数据失败: {str(e)}"}


@tool
@cached(key_prefix="earnings", ttl=86400)
async def get_earnings_history(ticker: str) -> dict:
    """
    获取公司历史财报数据（季度和年度）。
    - ticker: 股票代码
    返回最近几个季度和年度的营收、净利润、EPS等财报数据。
    适用于财报分析、业绩趋势判断、同比环比对比等场景。
    """
    logger.info(f"[get_earnings_history] 开始获取 {ticker} 的财报历史")
    
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        tk = yf.Ticker(ticker)
        
        # 使用新的 API：income_stmt 和 quarterly_income_stmt
        quarterly_income, annual_income = await asyncio.gather(
            loop.run_in_executor(None, lambda: tk.quarterly_income_stmt),
            loop.run_in_executor(None, lambda: tk.income_stmt)
        )

        result = {
            "ticker": ticker,
            "quarterly": [],
            "annual": [],
            "data_source": "财务数据服务",
        }

        # 处理季度数据
        if quarterly_income is not None and not quarterly_income.empty:
            # income_stmt 的数据是列为日期，行为指标
            for col in list(quarterly_income.columns)[:8]:  # 最近8个季度
                date_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
                
                # 从 income statement 中提取数据
                revenue = quarterly_income.loc["Total Revenue", col] if "Total Revenue" in quarterly_income.index else None
                net_income = quarterly_income.loc["Net Income", col] if "Net Income" in quarterly_income.index else None
                
                result["quarterly"].append({
                    "date": date_str,
                    "revenue": float(revenue) if revenue is not None and not pd.isna(revenue) else None,
                    "earnings": float(net_income) if net_income is not None and not pd.isna(net_income) else None,
                })

        # 处理年度数据
        if annual_income is not None and not annual_income.empty:
            # income_stmt 的数据是列为日期，行为指标
            for col in list(annual_income.columns)[:5]:  # 最近5年
                date_str = col.strftime("%Y") if hasattr(col, "strftime") else str(col)
                
                # 从 income statement 中提取数据
                revenue = annual_income.loc["Total Revenue", col] if "Total Revenue" in annual_income.index else None
                net_income = annual_income.loc["Net Income", col] if "Net Income" in annual_income.index else None
                
                result["annual"].append({
                    "year": date_str,
                    "revenue": float(revenue) if revenue is not None and not pd.isna(revenue) else None,
                    "earnings": float(net_income) if net_income is not None and not pd.isna(net_income) else None,
                })

        if not result["quarterly"] and not result["annual"]:
            logger.warning(f"[get_earnings_history] 未找到 {ticker} 的财报数据")
            return {"error": f"未找到 {ticker} 的财报数据"}

        logger.info(f"[get_earnings_history] 成功获取 {ticker} 财报: {len(result['quarterly'])} 个季度, {len(result['annual'])} 个年度")
        return result
        
    except Exception as e:
        logger.error(f"[get_earnings_history] 获取财报数据失败 {ticker}: {e}", exc_info=True)
        return {"error": f"获取财报数据失败: {str(e)}"}
