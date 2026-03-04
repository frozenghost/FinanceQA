"""Web search skill — real-time web search via Tavily."""

import logging

from langchain_core.tools import tool

from config.settings import settings
from services.cache_service import cached

logger = logging.getLogger(__name__)


@tool
@cached(key_prefix="web", ttl=900)
def search_web(query: str, max_results: int = 5) -> dict:
    """
    使用 Tavily 搜索引擎进行实时网络搜索，获取最新信息。
    - query: 搜索关键词，如 "阿里巴巴 2024 Q3 财报"
    - max_results: 返回结果数量，默认 5
    适用于知识库中没有的最新信息、实时事件、最新公告等。
    返回结果包含标题、内容摘要和来源 URL。
    """
    if not settings.TAVILY_API_KEY:
        return {"error": "Tavily API key 未配置，无法进行网络搜索"}

    try:
        from tavily import TavilyClient

        tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)
        response = tavily.search(query, max_results=max_results)

        results = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "content": r.get("content", ""),
                "url": r.get("url", ""),
                "score": r.get("score", 0),
            })

        return {
            "query": query,
            "results": results,
            "source": "tavily",
        }
    except Exception as e:
        logger.error(f"Tavily 搜索失败: {e}")
        return {"error": f"网络搜索失败: {str(e)}"}
