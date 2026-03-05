"""GET /api/market/{ticker} — direct market data endpoint."""

from fastapi import APIRouter

from skills.market_data.tool import get_real_time_quote

router = APIRouter()


@router.get("/api/market/{ticker}")
async def get_market(ticker: str):
    """Fetch real-time quote for a given ticker. Used by frontend TanStack Query."""
    result = get_real_time_quote.invoke({"ticker": ticker})
    return result
