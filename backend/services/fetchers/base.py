"""Base fetcher interface for knowledge sources."""

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.documents import Document


class BaseFetcher(ABC):
    """Abstract base class for all knowledge source fetchers."""

    def __init__(self, config: dict[str, Any]):
        """Initialize fetcher with configuration.
        
        Args:
            config: Fetcher-specific configuration dictionary
        """
        self.config = config

    @abstractmethod
    def fetch(self) -> list[Document]:
        """Fetch documents from the source.
        
        Returns:
            List of LangChain Document objects with content and metadata
        """
        pass

    def validate_config(self) -> bool:
        """Validate fetcher configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        return True
