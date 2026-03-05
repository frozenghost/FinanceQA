"""Unified skill registry — ALL_TOOLS for LangGraph Agent.

Skills are organized by functional domain:
- market_data: Real-time quotes and historical OHLCV data
- fundamentals: Company financials, valuation metrics, earnings
- technical_analysis: Technical indicators and trading signals
- news: Financial news and market sentiment
- research: Knowledge base search and web research
"""

from skills.market_data.tool import get_real_time_quote, get_historical_prices
from skills.fundamentals.tool import get_company_fundamentals, get_earnings_history
from skills.technical_analysis.tool import calculate_technical_indicators
from skills.news.tool import get_financial_news
from skills.research.tool import search_knowledge_base, search_web

ALL_TOOLS = [
    # Market data
    get_real_time_quote,
    get_historical_prices,
    
    # Fundamentals
    get_company_fundamentals,
    get_earnings_history,
    
    # Technical analysis
    calculate_technical_indicators,
    
    # News
    get_financial_news,
    
    # Research
    search_knowledge_base,
    search_web,
]
