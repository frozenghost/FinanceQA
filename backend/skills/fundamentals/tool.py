"""Fundamentals skill — company financials, valuation metrics, and earnings data."""

import logging

import pandas as pd
import yfinance as yf
from langchain_core.tools import tool

from services.cache_service import cached

logger = logging.getLogger(__name__)


@tool
@cached(key_prefix="fundamentals", ttl=86400)
def get_company_fundamentals(ticker: str) -> dict:
    """
    获取公司基本面数据和财务指标。
    - ticker: 股票代码
    返回市盈率、市净率、ROE、利润率、EPS、营收等关键财务指标。
    适用于基本面分析、估值评估、财务健康度判断等场景。
    """
    try:
        tk = yf.Ticker(ticker)
        info = tk.info

        if not info:
            return {"error": f"未找到 {ticker} 的基本面数据"}

        return {
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
            "data_source": "yfinance",
            "disclaimer": "数据来自公开财报，仅供参考",
        }
    except Exception as e:
        logger.error(f"获取基本面数据失败 {ticker}: {e}")
        return {"error": f"获取基本面数据失败: {str(e)}"}


def _row_value(df, index_contains: str):
    for i, label in enumerate(df.index):
        if index_contains.lower() in str(label).lower():
            return df.index[i]
    return None


def _income_stmt_to_periods(stmt, max_periods: int):
    if stmt is None or stmt.empty:
        return []
    revenue_row = _row_value(stmt, "total revenue") or _row_value(stmt, "revenue")
    net_income_row = _row_value(stmt, "net income")
    periods = []
    for col in list(stmt.columns)[:max_periods]:
        revenue = None
        earnings = None
        if revenue_row and revenue_row in stmt.index:
            v = stmt.loc[revenue_row, col]
            revenue = None if pd.isna(v) else float(v)
        if net_income_row and net_income_row in stmt.index:
            v = stmt.loc[net_income_row, col]
            earnings = None if pd.isna(v) else float(v)
        if revenue is not None or earnings is not None:
            periods.append({"revenue": revenue, "earnings": earnings, "date": col})
    return periods


@tool
@cached(key_prefix="earnings", ttl=86400)
def get_earnings_history(ticker: str) -> dict:
    """
    获取公司历史财报数据（季度和年度）。
    - ticker: 股票代码
    返回最近几个季度和年度的营收、净利润、EPS等财报数据。
    适用于财报分析、业绩趋势判断、同比环比对比等场景。
    """
    try:
        tk = yf.Ticker(ticker)
        quarterly_stmt = tk.quarterly_income_stmt
        annual_stmt = tk.income_stmt

        result = {
            "ticker": ticker,
            "quarterly": [],
            "annual": [],
            "data_source": "yfinance",
        }

        q_periods = _income_stmt_to_periods(quarterly_stmt, 8)
        for p in q_periods:
            date_val = p["date"]
            result["quarterly"].append({
                "date": date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val),
                "revenue": p["revenue"],
                "earnings": p["earnings"],
            })

        a_periods = _income_stmt_to_periods(annual_stmt, 5)
        for p in a_periods:
            date_val = p["date"]
            result["annual"].append({
                "year": str(date_val),
                "revenue": p["revenue"],
                "earnings": p["earnings"],
            })

        if not result["quarterly"] and not result["annual"]:
            return {"error": f"未找到 {ticker} 的财报数据"}

        return result
    except Exception as e:
        logger.error(f"获取财报数据失败 {ticker}: {e}")
        return {"error": f"获取财报数据失败: {str(e)}"}
