"""Web page fetcher using LangChain WebBaseLoader."""

import logging
from typing import Any

from langchain_community.document_loaders import WebBaseLoader
from langchain_core.documents import Document

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class WebPageFetcher(BaseFetcher):
    """Fetcher for static web pages."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.urls = config.get("urls", [])
        self.timeout = config.get("timeout", 30)
        self.retry_count = config.get("retry_count", 3)

    def validate_config(self) -> bool:
        if not self.urls:
            logger.error("WebPageFetcher: No URLs configured")
            return False
        return True

    def fetch(self) -> list[Document]:
        """Fetch documents from configured web pages."""
        if not self.validate_config():
            return []

        docs: list[Document] = []
        for url in self.urls:
            for attempt in range(self.retry_count):
                try:
                    loaded_docs = WebBaseLoader(url).load()
                    for doc in loaded_docs:
                        doc.metadata["source"] = url
                        doc.metadata["type"] = "web"
                        doc.metadata["fetcher"] = "WebPageFetcher"
                    docs.extend(loaded_docs)
                    logger.info(f"Loaded web page: {url}")
                    break
                except Exception as e:
                    if attempt == self.retry_count - 1:
                        logger.error(f"Failed to load page {url} after {self.retry_count} attempts: {e}")
                    else:
                        logger.warning(f"Retry {attempt + 1}/{self.retry_count} for {url}: {e}")

        return docs
