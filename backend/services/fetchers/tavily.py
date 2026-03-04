"""Tavily web search fetcher."""

import logging
from typing import Any

from langchain_core.documents import Document

from config.settings import settings
from .base import BaseFetcher

logger = logging.getLogger(__name__)


class TavilyFetcher(BaseFetcher):
    """Fetcher for Tavily web search results."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.queries = config.get("queries", [])
        self.max_results_per_query = config.get("max_results_per_query", 3)
        self.search_depth = config.get("search_depth", "advanced")

    def validate_config(self) -> bool:
        if not settings.TAVILY_API_KEY:
            logger.warning("TavilyFetcher: API key not configured, skipping")
            return False
        if not self.queries:
            logger.error("TavilyFetcher: No queries configured")
            return False
        return True

    def fetch(self) -> list[Document]:
        """Fetch documents from Tavily web search."""
        if not self.validate_config():
            return []

        docs: list[Document] = []
        try:
            from tavily import TavilyClient
            
            tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)

            for query in self.queries:
                try:
                    results = tavily.search(
                        query,
                        max_results=self.max_results_per_query,
                        search_depth=self.search_depth
                    )
                    
                    for result in results.get("results", []):
                        doc = Document(
                            page_content=result["content"],
                            metadata={
                                "source": result["url"],
                                "type": "tavily",
                                "fetcher": "TavilyFetcher",
                                "query": query,
                                "title": result.get("title", ""),
                                "score": result.get("score", 0.0)
                            }
                        )
                        docs.append(doc)
                    
                    logger.info(f"Loaded Tavily results for: {query}")
                except Exception as e:
                    logger.error(f"Tavily search failed for '{query}': {e}")

        except Exception as e:
            logger.error(f"Tavily client initialization failed: {e}")

        return docs
