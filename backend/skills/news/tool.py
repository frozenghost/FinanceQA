"""News and sentiment skill — financial news and market sentiment analysis."""

import asyncio
import logging
import re
from datetime import datetime
from typing import Annotated, Any, Optional

import httpx
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field, field_validator

from config.settings import settings
from services.cache_service import cached
from skills.common import run_sync, validate_non_empty

logger = logging.getLogger(__name__)

EXTRACT_URLS_LIMIT = 15
MIN_VERIFIED_CONTENT_LENGTH = 80

INVALID_URL_PHRASES = ("link not provided", "url not provided", "n/a", "")


def _is_valid_article_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    if not u.startswith(("http://", "https://")):
        return False
    return not any(phrase in u for phrase in INVALID_URL_PHRASES if phrase)


def _run_tavily_extract(urls: list[str], query: str = "") -> dict[str, Any]:
    from tavily import TavilyClient
    client = TavilyClient(api_key=settings.TAVILY_API_KEY)
    kwargs = {"urls": urls[:EXTRACT_URLS_LIMIT], "format": "text"}
    if query:
        kwargs["query"] = query
    return client.extract(**kwargs)


def _run_tavily_search(query: str, max_results: int) -> dict[str, Any]:
    from tavily import TavilyClient
    client = TavilyClient(api_key=settings.TAVILY_API_KEY)
    return client.search(query, max_results=max_results)


class GetFinancialNewsInput(BaseModel):
    """Schema for get_financial_news."""

    query: str = Field(
        description="Topic only: company name, industry, event, etc. Do not add time range; use analysis_start/analysis_end from state."
    )
    page_size: int = Field(default=10, ge=1, le=20, description="Number of news items to return")

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        return validate_non_empty(v, "query")


def _merge_articles(
    serpapi_articles: list[dict],
    serpapi_url_to_content: dict[str, str],
    tavily_results: list[dict],
    serpapi_verified_only: bool,
) -> list[dict]:
    """Merge results. SerpAPI: include only if verified by Tavily extract (when serpapi_verified_only)."""
    merged = []
    seen_urls: set[str] = set()

    for a in serpapi_articles:
        url = (a.get("url") or "").strip()
        if not _is_valid_article_url(url) or url in seen_urls:
            continue
        if serpapi_verified_only:
            content = serpapi_url_to_content.get(url) or ""
        else:
            content = serpapi_url_to_content.get(url) or a.get("description", "")
        if len((content or "").strip()) < MIN_VERIFIED_CONTENT_LENGTH:
            continue
        seen_urls.add(url)
        title = a.get("title", "") or "Link"
        merged.append({
            "title": title,
            "source": a.get("source", ""),
            "published_at": a.get("published_at", ""),
            "url": url,
            "link": f"[{title}]({url})",
            "content": content,
            "data_source": "news",
        })

    for r in tavily_results:
        url = (r.get("url") or "").strip()
        content = (r.get("content") or "").strip()
        if not _is_valid_article_url(url) or url in seen_urls:
            continue
        if len(content) < MIN_VERIFIED_CONTENT_LENGTH:
            continue
        seen_urls.add(url)
        title = r.get("title", "") or "Link"
        merged.append({
            "title": title,
            "source": r.get("source", "") or "news",
            "published_at": "",
            "url": url,
            "link": f"[{title}]({url})",
            "content": content,
            "data_source": "news",
        })

    return merged


def _cache_key_news(*args, **kwargs) -> str:
    query = (kwargs.get("query") or (args[0] if args else "") or "")[:60]
    page_size = kwargs.get("page_size", 10)
    start = kwargs.get("analysis_start") or ""
    end = kwargs.get("analysis_end") or ""
    return f"{query}_{page_size}_{start}_{end}".replace(" ", "_")


@tool(args_schema=GetFinancialNewsInput)
@cached(key_prefix="news", ttl=1800, key_extra=_cache_key_news)
async def get_financial_news(
    query: str,
    page_size: int = 10,
    analysis_start: Annotated[Optional[str], InjectedState("analysis_start")] = None,
    analysis_end: Annotated[Optional[str], InjectedState("analysis_end")] = None,
) -> dict:
    """
    Get latest financial news related to the query.
    Returns articles with title, source, url, content, and a ready-made Markdown link per
    article (field "link"). When presenting news in your answer, you must include the
    "link" for every article so users get a clickable link for each item.
    - query: Topic only (e.g. company name, industry, event). Do not add time range;
      time scope is applied via analysis_start/analysis_end from state.
    - page_size: Number of news items to return, default 10.
    """
    logger.info("get_financial_news called: query=%r, page_size=%s", query, page_size)
    if not settings.SERPAPI_KEY and not settings.TAVILY_API_KEY:
        logger.warning("Neither SerpAPI nor Tavily key configured")
        return {"error": "Neither SerpAPI nor Tavily key configured; cannot fetch news"}

    serpapi_articles: list[dict] = []
    serpapi_url_to_content: dict[str, str] = {}
    tavily_results: list[dict] = []

    if settings.SERPAPI_KEY:
        try:
            search_query = query
            if analysis_start and analysis_end:
                search_query = f"{query} after:{analysis_start} before:{analysis_end}"
            elif analysis_start:
                search_query = f"{query} after:{analysis_start}"
            elif analysis_end:
                search_query = f"{query} before:{analysis_end}"
            if analysis_start or analysis_end:
                logger.info("Date-scoped query=%r", search_query)

            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {
                    "engine": "google_news",
                    "q": search_query,
                    "api_key": settings.SERPAPI_KEY,
                    "num": page_size,
                    "gl": "us",
                    "hl": "en",
                }
                response = await client.get("https://serpapi.com/search", params=params)
                response.raise_for_status()
                data = response.json()

            raw_list = data.get("news_results", [])
            
            if analysis_start or analysis_end:
                start_dt = None
                end_dt = None
                if analysis_start:
                    start_dt = datetime.strptime(analysis_start, "%Y-%m-%d")
                if analysis_end:
                    end_dt = datetime.strptime(analysis_end, "%Y-%m-%d")
                filtered_list = []
                for item in raw_list:
                    iso_date_str = item.get("iso_date", "")
                    if iso_date_str:
                        try:
                            item_dt = datetime.fromisoformat(iso_date_str.replace("Z", "+00:00"))
                            item_dt = item_dt.replace(tzinfo=None)
                            if start_dt and item_dt < start_dt:
                                continue
                            if end_dt and item_dt > end_dt:
                                continue
                        except ValueError:
                            pass
                    filtered_list.append(item)
                raw_list = filtered_list[:page_size]
            else:
                raw_list = raw_list[:page_size]
            
            logger.info("SerpAPI Google News returned %d filtered items", len(raw_list))
            for item in raw_list:
                link = (item.get("link") or "").strip()
                if not _is_valid_article_url(link):
                    continue
                source_val = item.get("source")
                source_name = (
                    source_val.get("name", "") if isinstance(source_val, dict) else (source_val or "")
                )
                serpapi_articles.append({
                    "title": item.get("title", ""),
                    "source": source_name,
                    "published_at": item.get("date", ""),
                    "description": item.get("snippet", ""),
                    "url": link,
                })
        except Exception as e:
            logger.error(f"SerpAPI request failed: {e}")
            # Continue with Tavily-only if available

    if settings.TAVILY_API_KEY:
        # Enrich SerpAPI URLs with Tavily extract
        urls_to_extract = [a["url"] for a in serpapi_articles if a.get("url")][:EXTRACT_URLS_LIMIT]
        logger.info("Tavily extract verifying %d SerpAPI URLs", len(urls_to_extract))
        if urls_to_extract:
            try:
                extract_res = await asyncio.wait_for(
                    run_sync(
                        lambda: _run_tavily_extract(urls_to_extract, query),
                    ),
                    timeout=30.0,
                )
                for res in extract_res.get("results", []):
                    url = res.get("url", "")
                    raw = res.get("raw_content", "") or res.get("content", "")
                    if url and raw:
                        serpapi_url_to_content[url] = raw
                logger.info("Tavily extract enriched %d URLs", len(serpapi_url_to_content))
            except asyncio.TimeoutError:
                logger.warning("Tavily extract timed out")
            except Exception as e:
                logger.warning(f"Tavily extract failed: {e}")

        # Tavily search for related news
        try:
            search_res = await asyncio.wait_for(
                run_sync(
                    lambda: _run_tavily_search(query, max_results=page_size),
                ),
                timeout=15.0,
            )
            for r in search_res.get("results", []):
                tavily_results.append({
                    "title": r.get("title", ""),
                    "content": r.get("content", ""),
                    "url": r.get("url", ""),
                    "source": r.get("source", "Tavily"),
                })
            logger.info("Tavily search returned %d results", len(tavily_results))
        except asyncio.TimeoutError:
            logger.warning("Tavily search timed out")
        except Exception as e:
            logger.warning(f"Tavily search failed: {e}")

    articles = _merge_articles(
        serpapi_articles,
        serpapi_url_to_content,
        tavily_results,
        serpapi_verified_only=bool(settings.TAVILY_API_KEY),
    )
    data_sources = ["news"] if articles else []

    logger.info(
        "get_financial_news done: query=%r, total_articles=%d, sources=%s",
        query, len(articles), data_sources,
    )
    return {
        "query": query,
        "articles": articles,
        "total_results": len(articles),
        "data_sources": data_sources,
    }
