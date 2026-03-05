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
    获取与查询相关的最新金融新闻。
    - query: 搜索关键词，如公司名称、行业、事件等
    - page_size: 返回新闻数量，默认 5 条
    返回新闻标题、来源、发布时间、摘要和链接。
    适用于了解最新市场动态、公司新闻、行业事件等场景。
    """
    if not settings.SERPAPI_KEY:
        return {"error": "SerpAPI key 未配置，无法获取新闻"}

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
        logger.error(f"SerpAPI 请求失败: {e}")
        return {"error": f"新闻获取失败: {str(e)}"}
