"""Wikipedia fetcher using LangChain WikipediaLoader."""

import logging
from typing import Any

from langchain_community.document_loaders import WikipediaLoader
from langchain_core.documents import Document

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class WikipediaFetcher(BaseFetcher):
    """Fetcher for Wikipedia articles."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.queries = config.get("queries", [])
        self.max_docs_per_query = config.get("max_docs_per_query", 1)

    def validate_config(self) -> bool:
        if not self.queries:
            logger.error("WikipediaFetcher: No queries configured")
            return False
        return True

    def fetch(self) -> list[Document]:
        """Fetch documents from Wikipedia."""
        if not self.validate_config():
            return []

        docs: list[Document] = []
        for query in self.queries:
            try:
                # Auto-detect language based on Chinese characters
                lang = "zh" if any("\u4e00" <= c <= "\u9fff" for c in query) else "en"
                loaded_docs = WikipediaLoader(
                    query=query,
                    load_max_docs=self.max_docs_per_query,
                    lang=lang
                ).load()
                
                for doc in loaded_docs:
                    doc.metadata["type"] = "wiki"
                    doc.metadata["fetcher"] = "WikipediaFetcher"
                    doc.metadata["query"] = query
                    doc.metadata["language"] = lang
                
                docs.extend(loaded_docs)
                logger.info(f"Loaded Wikipedia article: {query} (lang={lang})")
            except Exception as e:
                logger.error(f"Wikipedia fetch failed for '{query}': {e}")

        return docs
