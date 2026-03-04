"""News skill — fetches financial news via NewsAPI with LLM-friendly summaries."""

import logging

from langchain_core.tools import tool
from newsapi import NewsApiClient

from config.settings import settings
from services.cache_service import cached

logger = logging.getLogger(__name__)


@tool
@cached(key_prefix="news", ttl=1800)
def get_financial_news(query: str, page_size: int = 5) -> dict:
    """
    获取与查询相关的最新金融新闻。
    - query: 搜索关键词，如 "阿里巴巴财报"、"Tesla earnings"
    - page_size: 返回新闻数量，默认 5 条
    返回新闻标题、来源、发布时间和摘要的列表。
    """
    if not settings.NEWSAPI_KEY:
        return {"error": "NewsAPI key 未配置，无法获取新闻"}

    try:
        newsapi = NewsApiClient(api_key=settings.NEWSAPI_KEY)
        response = newsapi.get_everything(
            q=query,
            language="en",
            sort_by="publishedAt",
            page_size=page_size,
        )

        articles = []
        for article in response.get("articles", []):
            articles.append({
                "title": article.get("title", ""),
                "source": article.get("source", {}).get("name", ""),
                "published_at": article.get("publishedAt", ""),
                "description": article.get("description", ""),
                "url": article.get("url", ""),
            })

        return {
            "query": query,
            "total_results": response.get("totalResults", 0),
            "articles": articles,
        }
    except Exception as e:
        logger.error(f"NewsAPI 请求失败: {e}")
        return {"error": f"新闻获取失败: {str(e)}"}
