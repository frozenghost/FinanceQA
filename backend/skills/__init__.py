"""Unified skill registry — ALL_TOOLS for LangGraph Agent."""

from skills.market_data.tool import get_market_data
from skills.news.tool import get_financial_news
from skills.rag_search.tool import search_knowledge_base
from skills.web_search.tool import search_web
from skills.technical_metrics.tool import get_technical_indicators

ALL_TOOLS = [
    get_market_data,
    get_financial_news,
    search_knowledge_base,
    search_web,
    get_technical_indicators,
]
