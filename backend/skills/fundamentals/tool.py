"""Fundamentals skill — company financials, valuation metrics, and earnings data."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Annotated, Any, Optional

import pandas as pd
import yfinance as yf
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field, field_validator

from services.cache_service import cached
from skills.common import run_sync, validate_non_empty

logger = logging.getLogger(__name__)

# Max gap between latest earnings and analysis window: one quarter (days)
MAX_EARNINGS_QUARTER_DAYS = 92


class GetCompanyFundamentalsInput(BaseModel):
    """Schema for get_company_fundamentals."""

    ticker: str = Field(description="Stock symbol")

    @field_validator("ticker")
    @classmethod
    def ticker_not_empty(cls, v: str) -> str:
        return validate_non_empty(v, "ticker")


class GetEarningsHistoryInput(BaseModel):
    """Schema for get_earnings_history."""

    ticker: str = Field(description="Stock symbol")

    @field_validator("ticker")
    @classmethod
    def ticker_not_empty(cls, v: str) -> str:
        return validate_non_empty(v, "ticker")


def _cache_key_fundamentals(*args, **kwargs) -> str:
    return (kwargs.get("ticker") or (args[0] if args else "") or "").strip()


@tool(args_schema=GetCompanyFundamentalsInput)
@cached(key_prefix="fundamentals", ttl=86400, key_extra=_cache_key_fundamentals)
async def get_company_fundamentals(ticker: str) -> dict:
    """
    Get company fundamental data and financial metrics.
    - ticker: Stock symbol
    Returns key financial indicators such as P/E ratio, P/B ratio, ROE, profit margin, EPS, revenue, etc.
    Suitable for fundamental analysis, valuation assessment, and financial health evaluation.
    """
    logger.info(f"[get_company_fundamentals] Starting to fetch fundamentals for {ticker}")

    try:
        tk = yf.Ticker(ticker)
        info = await run_sync(lambda: tk.info)

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


def _safe_get(df: pd.DataFrame, row_names: list[str], col: Any) -> Optional[float]:
    for name in row_names:
        if name in df.index:
            val = df.loc[name, col]
            if val is not None and not pd.isna(val):
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass
    return None


def _income_quarter(
    income_df: pd.DataFrame, col: Any, date_fmt: str = "%Y-%m-%d"
) -> Optional[dict]:
    if income_df is None or income_df.empty:
        return None
    date_str = col.strftime(date_fmt) if hasattr(col, "strftime") else str(col)
    revenue = _safe_get(income_df, ["Total Revenue", "Revenue"], col)
    net_income = _safe_get(income_df, ["Net Income"], col)
    operating_income = _safe_get(income_df, ["Operating Income", "Operating Income Loss"], col)
    gross_profit = _safe_get(income_df, ["Gross Profit"], col)
    cost_of_revenue = _safe_get(income_df, ["Cost of Revenue", "Cost Of Revenue"], col)
    eps = _safe_get(income_df, ["Diluted EPS", "Basic EPS"], col)
    out = {
        "date": date_str,
        "revenue": revenue,
        "earnings": net_income,
        "operating_income": operating_income,
        "gross_profit": gross_profit,
        "cost_of_revenue": cost_of_revenue,
        "eps": eps,
    }
    if revenue and net_income:
        out["profit_margin"] = round(net_income / revenue * 100, 2)
    if revenue and operating_income is not None:
        out["operating_margin"] = round(operating_income / revenue * 100, 2)
    if revenue and gross_profit is not None:
        out["gross_margin"] = round(gross_profit / revenue * 100, 2)
    return out


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    s = s.strip()[:10]
    if len(s) != 10:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return None


def _latest_earnings_date(result: dict) -> Optional[datetime]:
    dates: list[datetime] = []
    for q in result.get("quarterly") or []:
        d = _parse_date(q.get("date"))
        if d:
            dates.append(d)
    for e in result.get("earnings_dates") or []:
        d = _parse_date(e.get("date") or e.get("earnings_date"))
        if d:
            dates.append(d)
    for e in result.get("earnings_surprise") or []:
        d = _parse_date(e.get("date"))
        if d:
            dates.append(d)
    return max(dates) if dates else None


def _in_earnings_window(d: Optional[datetime], window_start: datetime, window_end: datetime) -> bool:
    if d is None:
        return False
    return window_start <= d <= window_end


def _filter_earnings_by_window(result: dict, analysis_start: str, analysis_end: str) -> None:
    """Keep only earnings within [analysis_start - 92d, analysis_end + 92d]; rebuild chart_series."""
    start_d = _parse_date(analysis_start)
    end_d = _parse_date(analysis_end)
    if not start_d or not end_d:
        return
    window_start = start_d - timedelta(days=MAX_EARNINGS_QUARTER_DAYS)
    window_end = end_d + timedelta(days=MAX_EARNINGS_QUARTER_DAYS)

    def filter_quarterly() -> None:
        q_list = result.get("quarterly") or []
        kept = [row for row in q_list if _in_earnings_window(_parse_date(row.get("date")), window_start, window_end)]
        result["quarterly"] = kept
        cs_q = result["chart_series"]["quarterly"]
        cs_q["labels"] = [r["date"] for r in kept]
        cs_q["revenue"] = [r.get("revenue") for r in kept]
        cs_q["earnings"] = [r.get("earnings") for r in kept]
        cs_q["eps"] = [r.get("eps") for r in kept]
        cs_q["profit_margin"] = [r.get("profit_margin") for r in kept]
        cs_q["operating_margin"] = [r.get("operating_margin") for r in kept]

    def filter_annual() -> None:
        a_list = result.get("annual") or []
        cs_a = result["chart_series"]["annual"]
        kept = []
        for i, row in enumerate(a_list):
            year_s = row.get("year") or row.get("date")
            if year_s:
                try:
                    d = datetime.strptime(str(year_s).strip()[:4], "%Y")
                except ValueError:
                    d = None
            else:
                d = None
            if _in_earnings_window(d, window_start, window_end):
                kept.append(row)
        result["annual"] = kept
        cs_a["labels"] = [r.get("year") for r in kept]
        cs_a["revenue"] = [r.get("revenue") for r in kept]
        cs_a["earnings"] = [r.get("earnings") for r in kept]
        cs_a["eps"] = [r.get("eps") for r in kept]
        cs_a["profit_margin"] = [r.get("profit_margin") for r in kept]
        cs_a["operating_margin"] = [r.get("operating_margin") for r in kept]

    def filter_surprise() -> None:
        e_list = result.get("earnings_surprise") or []
        cs_e = result["chart_series"]["eps_surprise"]
        kept = [e for e in e_list if _in_earnings_window(_parse_date(e.get("date")), window_start, window_end)]
        result["earnings_surprise"] = kept
        cs_e["dates"] = [e.get("date") for e in kept]
        cs_e["eps_actual"] = [e.get("epsActual") for e in kept]
        cs_e["eps_estimate"] = [e.get("epsEstimate") for e in kept]
        cs_e["surprise_percent"] = [e.get("surprise_percent") for e in kept]

    def filter_dates() -> None:
        e_list = result.get("earnings_dates") or []
        kept = [
            e for e in e_list
            if _in_earnings_window(
                _parse_date(e.get("date") or e.get("earnings_date")), window_start, window_end
            )
        ]
        result["earnings_dates"] = kept

    filter_quarterly()
    filter_annual()
    filter_surprise()
    filter_dates()


def _cache_key_earnings(*args, **kwargs) -> str:
    ticker = (kwargs.get("ticker") or (args[0] if args else "") or "").strip()
    start = kwargs.get("analysis_start") or ""
    end = kwargs.get("analysis_end") or ""
    return f"{ticker}_{start}_{end}"


@tool(args_schema=GetEarningsHistoryInput)
@cached(key_prefix="earnings", ttl=86400, key_extra=_cache_key_earnings)
async def get_earnings_history(
    ticker: str,
    analysis_start: Annotated[Optional[str], InjectedState("analysis_start")] = None,
    analysis_end: Annotated[Optional[str], InjectedState("analysis_end")] = None,
) -> dict:
    """
    Get company historical earnings data (quarterly and annual) plus EPS surprise history.
    - ticker: Stock symbol
    Returns revenue, net income, operating income, margins, EPS, and chart-ready time series.
    When state has analysis_start/analysis_end, only returns earnings if the latest report is within one quarter of the analysis window; otherwise returns no_earnings_in_range.
    Suitable for earnings analysis, trend evaluation, YoY/QoQ comparisons, and frontend charts.
    """
    logger.info(f"[get_earnings_history] Starting to fetch earnings history for {ticker}")

    try:
        tk = yf.Ticker(ticker)
        quarterly_income, annual_income, earnings_hist_df, earnings_dates_df = await asyncio.gather(
            run_sync(lambda: tk.quarterly_income_stmt),
            run_sync(lambda: tk.income_stmt),
            run_sync(lambda: tk.get_earnings_history()),
            run_sync(lambda: tk.get_earnings_dates(limit=16)),
        )

        result = {
            "ticker": ticker,
            "quarterly": [],
            "annual": [],
            "earnings_surprise": [],
            "earnings_dates": [],
            "chart_series": {
                "quarterly": {"labels": [], "revenue": [], "earnings": [], "eps": [], "profit_margin": [], "operating_margin": []},
                "annual": {"labels": [], "revenue": [], "earnings": [], "eps": [], "profit_margin": [], "operating_margin": []},
                "eps_surprise": {"dates": [], "eps_actual": [], "eps_estimate": [], "surprise_percent": []},
            },
            "data_source": "Financial Data Service",
        }

        if quarterly_income is not None and not quarterly_income.empty:
            for col in list(quarterly_income.columns)[:8]:
                row = _income_quarter(quarterly_income, col)
                if row:
                    result["quarterly"].append(row)
                    result["chart_series"]["quarterly"]["labels"].append(row["date"])
                    result["chart_series"]["quarterly"]["revenue"].append(row["revenue"])
                    result["chart_series"]["quarterly"]["earnings"].append(row["earnings"])
                    result["chart_series"]["quarterly"]["eps"].append(row.get("eps"))
                    result["chart_series"]["quarterly"]["profit_margin"].append(row.get("profit_margin"))
                    result["chart_series"]["quarterly"]["operating_margin"].append(row.get("operating_margin"))

        if annual_income is not None and not annual_income.empty:
            for col in list(annual_income.columns)[:5]:
                row = _income_quarter(annual_income, col, date_fmt="%Y")
                if row:
                    row["year"] = row.pop("date")
                    result["annual"].append(row)
                    result["chart_series"]["annual"]["labels"].append(row["year"])
                    result["chart_series"]["annual"]["revenue"].append(row["revenue"])
                    result["chart_series"]["annual"]["earnings"].append(row["earnings"])
                    result["chart_series"]["annual"]["eps"].append(row.get("eps"))
                    result["chart_series"]["annual"]["profit_margin"].append(row.get("profit_margin"))
                    result["chart_series"]["annual"]["operating_margin"].append(row.get("operating_margin"))

        if earnings_hist_df is not None and not earnings_hist_df.empty:
            for idx in list(earnings_hist_df.index)[:12]:
                date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
                row = {"date": date_str}
                for c in ("epsEstimate", "epsActual", "epsDifference", "surprisePercent"):
                    if c in earnings_hist_df.columns:
                        v = earnings_hist_df.loc[idx, c]
                        if v is not None and not pd.isna(v):
                            key = "surprise_percent" if c == "surprisePercent" else c
                            row[key] = float(v)
                result["earnings_surprise"].append(row)
                result["chart_series"]["eps_surprise"]["dates"].append(date_str)
                result["chart_series"]["eps_surprise"]["eps_actual"].append(row.get("epsActual"))
                result["chart_series"]["eps_surprise"]["eps_estimate"].append(row.get("epsEstimate"))
                result["chart_series"]["eps_surprise"]["surprise_percent"].append(row.get("surprise_percent"))

        if earnings_dates_df is not None and not earnings_dates_df.empty:
            cols = earnings_dates_df.columns.tolist()
            for idx in list(earnings_dates_df.index)[:8]:
                date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
                entry = {"date": date_str}
                if "Earnings Date" in cols:
                    ed = earnings_dates_df.loc[idx, "Earnings Date"]
                    if hasattr(ed, "strftime"):
                        entry["earnings_date"] = ed.strftime("%Y-%m-%d")
                    else:
                        entry["earnings_date"] = str(ed) if ed is not None and not pd.isna(ed) else None
                for k in ("Reported EPS", "Estimated EPS", "Surprise(%)"):
                    if k in cols:
                        v = earnings_dates_df.loc[idx, k]
                        if v is not None and not pd.isna(v):
                            key = "reported_eps" if k == "Reported EPS" else "estimated_eps" if k == "Estimated EPS" else "surprise_pct"
                            entry[key] = float(v)
                result["earnings_dates"].append(entry)

        if not result["quarterly"] and not result["annual"] and not result["earnings_surprise"]:
            logger.warning(f"[get_earnings_history] No earnings data found for {ticker}")
            return {"error": f"No earnings data found for {ticker}"}

        if analysis_start and analysis_end:
            start_d = _parse_date(analysis_start)
            latest = _latest_earnings_date(result)
            if start_d and latest:
                gap_days = (start_d - latest).days
                if gap_days > MAX_EARNINGS_QUARTER_DAYS:
                    logger.info(
                        f"[get_earnings_history] Latest earnings {latest.date()} is {gap_days} days before analysis start {analysis_start}; beyond one quarter, returning no_earnings_in_range"
                    )
                    return {
                        "ticker": ticker,
                        "quarterly": [],
                        "annual": [],
                        "earnings_surprise": [],
                        "earnings_dates": [],
                        "chart_series": {
                            "quarterly": {"labels": [], "revenue": [], "earnings": [], "eps": [], "profit_margin": [], "operating_margin": []},
                            "annual": {"labels": [], "revenue": [], "earnings": [], "eps": [], "profit_margin": [], "operating_margin": []},
                            "eps_surprise": {"dates": [], "eps_actual": [], "eps_estimate": [], "surprise_percent": []},
                        },
                        "no_earnings_in_range": True,
                        "reason": "Latest earnings report is more than one quarter before the analysis time window.",
                        "data_source": "Financial Data Service",
                    }
            _filter_earnings_by_window(result, analysis_start, analysis_end)

        logger.info(
            f"[get_earnings_history] Successfully fetched {ticker} earnings: "
            f"{len(result['quarterly'])} quarters, {len(result['annual'])} years, "
            f"{len(result['earnings_surprise'])} eps surprises"
        )
        return result

    except Exception as e:
        logger.error(f"[get_earnings_history] Failed to fetch earnings for {ticker}: {e}", exc_info=True)
        return {"error": f"Failed to fetch earnings: {str(e)}"}
