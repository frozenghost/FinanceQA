"""News and sentiment skill — financial news and market sentiment analysis."""

import logging
from typing import Optional

import httpx
from langchain_core.tools import tool

from config.settings import settings
from services.cache_service import cached

logger = logging.getLogger(__name__)


@tool
@cached(key_prefix="news", ttl=1800)
async def get_financial_news(query: str, page_size: int = 5) -> dict:
    """
    Get latest financial news related to the query.
    - query: Search keywords, such as company name, industry, event, etc.
    - page_size: Number of news items to return, default 5
    Returns news title, source, publication time, summary, and link.
    Suitable for understanding latest market dynamics, company news, industry events, etc.
    """
    if not settings.SERPAPI_KEY:
        return {"error": "SerpAPI key not configured, cannot fetch news"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {
                "engine": "google_news",
                "q": query,
                "api_key": settings.SERPAPI_KEY,
                "num": page_size,
                "gl": "us",
                "hl": "en",
            }
            
            response = await client.get(
                "https://serpapi.com/search",
                params=params
            )
            response.raise_for_status()
            data = response.json()

        articles = []
        news_results = data.get("news_results", [])
        
        for item in news_results[:page_size]:
            articles.append({
                "title": item.get("title", ""),
                "source": item.get("source", {}).get("name", "") if isinstance(item.get("source"), dict) else item.get("source", ""),
                "published_at": item.get("date", ""),
                "description": item.get("snippet", ""),
                "url": item.get("link", ""),
            })

        return {
            "query": query,
            "total_results": len(news_results),
            "articles": articles,
            "data_source": "SerpAPI Google News",
        }
    
    except Exception as e:
        logger.error(f"SerpAPI request failed: {e}")
        return {"error": f"Failed to fetch news: {str(e)}"}
