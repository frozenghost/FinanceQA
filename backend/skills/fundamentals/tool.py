"""Fundamentals skill — company financials, valuation metrics, and earnings data."""

import logging

import pandas as pd
import yfinance as yf
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

from services.cache_service import cached

logger = logging.getLogger(__name__)


class GetCompanyFundamentalsInput(BaseModel):
    """Schema for get_company_fundamentals."""

    ticker: str = Field(description="Stock symbol")

    @field_validator("ticker")
    @classmethod
    def ticker_not_empty(cls, v: str) -> str:
        t = (v or "").strip()
        if not t:
            raise ValueError("ticker must be non-empty")
        return t


class GetEarningsHistoryInput(BaseModel):
    """Schema for get_earnings_history."""

    ticker: str = Field(description="Stock symbol")

    @field_validator("ticker")
    @classmethod
    def ticker_not_empty(cls, v: str) -> str:
        t = (v or "").strip()
        if not t:
            raise ValueError("ticker must be non-empty")
        return t


@tool(args_schema=GetCompanyFundamentalsInput)
@cached(key_prefix="fundamentals", ttl=86400)
async def get_company_fundamentals(ticker: str) -> dict:
    """
    Get company fundamental data and financial metrics.
    - ticker: Stock symbol
    Returns key financial indicators such as P/E ratio, P/B ratio, ROE, profit margin, EPS, revenue, etc.
    Suitable for fundamental analysis, valuation assessment, and financial health evaluation.
    """
    logger.info(f"[get_company_fundamentals] Starting to fetch fundamentals for {ticker}")
    
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        tk = yf.Ticker(ticker)
        info = await loop.run_in_executor(None, lambda: tk.info)

        if not info:
            logger.warning(f"[get_company_fundamentals] No fundamentals found for {ticker}")
            return {"error": f"No fundamentals found for {ticker}"}

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
            "data_source": "Financial Data Service",
            "disclaimer": "Data from public filings, for reference only",
        }
        
        logger.info(f"[get_company_fundamentals] Successfully fetched {ticker} fundamentals: PE={result['valuation']['pe_ratio']}, ROE={result['profitability']['roe']}")
        return result
        
    except Exception as e:
        logger.error(f"[get_company_fundamentals] Failed to fetch fundamentals for {ticker}: {e}", exc_info=True)
        return {"error": f"Failed to fetch fundamentals: {str(e)}"}


@tool(args_schema=GetEarningsHistoryInput)
@cached(key_prefix="earnings", ttl=86400)
async def get_earnings_history(ticker: str) -> dict:
    """
    Get company historical earnings data (quarterly and annual).
    - ticker: Stock symbol
    Returns revenue, net income, EPS and other earnings data for recent quarters and years.
    Suitable for earnings analysis, performance trend evaluation, YoY and QoQ comparisons.
    """
    logger.info(f"[get_earnings_history] Starting to fetch earnings history for {ticker}")
    
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        tk = yf.Ticker(ticker)
        
        # Use new API: income_stmt and quarterly_income_stmt
        quarterly_income, annual_income = await asyncio.gather(
            loop.run_in_executor(None, lambda: tk.quarterly_income_stmt),
            loop.run_in_executor(None, lambda: tk.income_stmt)
        )

        result = {
            "ticker": ticker,
            "quarterly": [],
            "annual": [],
            "data_source": "Financial Data Service",
        }

        # Process quarterly data
        if quarterly_income is not None and not quarterly_income.empty:
            # Data is columns as dates, rows as metrics
            for col in list(quarterly_income.columns)[:8]:  # Last 8 quarters
                date_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
                
                # Extract data from income statement
                revenue = quarterly_income.loc["Total Revenue", col] if "Total Revenue" in quarterly_income.index else None
                net_income = quarterly_income.loc["Net Income", col] if "Net Income" in quarterly_income.index else None
                
                result["quarterly"].append({
                    "date": date_str,
                    "revenue": float(revenue) if revenue is not None and not pd.isna(revenue) else None,
                    "earnings": float(net_income) if net_income is not None and not pd.isna(net_income) else None,
                })

        # Process annual data
        if annual_income is not None and not annual_income.empty:
            # Data is columns as dates, rows as metrics
            for col in list(annual_income.columns)[:5]:  # Last 5 years
                date_str = col.strftime("%Y") if hasattr(col, "strftime") else str(col)
                
                # Extract data from income statement
                revenue = annual_income.loc["Total Revenue", col] if "Total Revenue" in annual_income.index else None
                net_income = annual_income.loc["Net Income", col] if "Net Income" in annual_income.index else None
                
                result["annual"].append({
                    "year": date_str,
                    "revenue": float(revenue) if revenue is not None and not pd.isna(revenue) else None,
                    "earnings": float(net_income) if net_income is not None and not pd.isna(net_income) else None,
                })

        if not result["quarterly"] and not result["annual"]:
            logger.warning(f"[get_earnings_history] No earnings data found for {ticker}")
            return {"error": f"No earnings data found for {ticker}"}

        logger.info(f"[get_earnings_history] Successfully fetched {ticker} earnings: {len(result['quarterly'])} quarters, {len(result['annual'])} years")
        return result
        
    except Exception as e:
        logger.error(f"[get_earnings_history] Failed to fetch earnings for {ticker}: {e}", exc_info=True)
        return {"error": f"Failed to fetch earnings: {str(e)}"}
