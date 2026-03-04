"""GET /api/market/{ticker} — direct market data endpoint."""

from fastapi import APIRouter

from skills.market_data.tool import get_market_data

router = APIRouter()


@router.get("/api/market/{ticker}")
async def get_market(ticker: str, period: str = "7d"):
    """Fetch market data for a given ticker. Used by frontend TanStack Query."""
    # get_market_data is a LangChain tool; call its underlying function
    result = get_market_data.invoke({"ticker": ticker, "period": period})
    return result
