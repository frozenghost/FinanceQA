"""Knowledge base manager with pluggable fetchers."""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional, Union

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config.settings import settings
from services.embedding import get_embeddings
from services.fetchers import (
    BaseFetcher,
    LocalFileFetcher,
    TavilyFetcher,
    WebPageFetcher,
    WikipediaFetcher,
    YahooFinanceFetcher,
)

logger = logging.getLogger(__name__)

# Fetcher registry mapping type names to classes
FETCHER_REGISTRY: dict[str, type[BaseFetcher]] = {
    "WebPageFetcher": WebPageFetcher,
    "WikipediaFetcher": WikipediaFetcher,
    "YahooFinanceFetcher": YahooFinanceFetcher,
    "TavilyFetcher": TavilyFetcher,
    "LocalFileFetcher": LocalFileFetcher,
}


class KnowledgeManager:
    """Manages knowledge base refresh with configurable sources."""

    def __init__(self, config_path: Optional[Union[str, Path]] = None) -> None:
        """Initialize knowledge manager.
        
        Args:
            config_path: Path to knowledge sources JSON config file.
                        Defaults to backend/config/knowledge_sources.json
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "knowledge_sources.json"
        
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from JSON file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        logger.info(f"Loaded knowledge sources config from {self.config_path}")
        return config

    def _create_splitter(self, source_name: Optional[str]) -> RecursiveCharacterTextSplitter:
        """Create text splitter from config; use by_source[source_name] if present else global chunking."""
        chunking = self.config.get("chunking", {})
        base = dict(chunking)
        base.pop("by_source", None)
        overrides = (chunking.get("by_source") or {}).get(source_name or "") if source_name else {}
        overrides = overrides if isinstance(overrides, dict) else {}
        merged = {**base, **overrides}
        return RecursiveCharacterTextSplitter(
            chunk_size=merged.get("chunk_size", 1024),
            chunk_overlap=merged.get("chunk_overlap", 128),
            separators=merged.get("separators", ["\n\n", "\n", ".", " "]),
            length_function=len,
            is_separator_regex=False,
        )

    def _get_vectordb(self, use_embedding_cache: bool = True) -> Chroma:
        """Get or create vector database instance. use_embedding_cache=False skips Redis (e.g. for refresh)."""
        vectordb_config = self.config.get("vectordb", {})
        
        collection_name = vectordb_config.get("collection_name", "finance_knowledge")
        persist_dir = vectordb_config.get("persist_directory", settings.CHROMA_DIR)
        
        # Support environment variable substitution
        if persist_dir.startswith("${") and persist_dir.endswith("}"):
            env_var = persist_dir[2:-1]
            persist_dir = getattr(settings, env_var, settings.CHROMA_DIR)
        
        return Chroma(
            collection_name=collection_name,
            embedding_function=get_embeddings(use_cache=use_embedding_cache),
            persist_directory=persist_dir,
        )

    def _create_fetcher(self, source_config: dict[str, Any]) -> Optional[BaseFetcher]:
        """Create a fetcher instance from source configuration.
        
        Args:
            source_config: Source configuration dictionary
            
        Returns:
            Fetcher instance or None if fetcher type not found
        """
        fetcher_name = source_config.get("fetcher")
        if not fetcher_name:
            logger.error(f"No fetcher specified for source: {source_config.get('name')}")
            return None
        
        fetcher_class = FETCHER_REGISTRY.get(fetcher_name)
        if not fetcher_class:
            logger.error(f"Unknown fetcher type: {fetcher_name}")
            return None
        
        try:
            fetcher = fetcher_class(source_config.get("config", {}))
            return fetcher
        except Exception as e:
            logger.error(f"Failed to create fetcher {fetcher_name}: {e}")
            return None

    def _fetch_from_source(self, source_config: dict[str, Any]) -> tuple[str, list[Document]]:
        """Fetch documents from a single source (thread-safe).
        
        Args:
            source_config: Source configuration dictionary
            
        Returns:
            Tuple of (source_name, documents)
        """
        source_name = source_config.get("name", "unknown")
        
        if not source_config.get("enabled", True):
            logger.info(f"Skipping disabled source: {source_name}")
            return source_name, []
        
        logger.info(f"Fetching from source: {source_name}")
        
        fetcher = self._create_fetcher(source_config)
        if not fetcher:
            return source_name, []
        
        try:
            docs = fetcher.fetch()
            for doc in docs:
                doc.metadata["source_name"] = source_name
            logger.info(f"Fetched {len(docs)} documents from {source_name}")
            return source_name, docs
        except Exception as e:
            logger.error(f"Error fetching from {source_name}: {e}")
            return source_name, []

    async def fetch_all_documents_async(self) -> list[Document]:
        """Fetch documents from all enabled sources concurrently.
        
        Returns:
            List of all fetched documents
        """
        sources = self.config.get("sources", [])
        
        if not sources:
            logger.warning("No sources configured")
            return []
        
        logger.info(f"Starting concurrent fetch from {len(sources)} sources")
        
        # Use ThreadPoolExecutor for I/O-bound operations
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=len(sources)) as executor:
            # Submit all fetch tasks concurrently
            tasks = [
                loop.run_in_executor(executor, self._fetch_from_source, source_config)
                for source_config in sources
            ]
            
            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect all documents
        all_docs: list[Document] = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Fetch task failed with exception: {result}")
                continue
            
            source_name, docs = result
            all_docs.extend(docs)
        
        logger.info(f"Concurrent fetch complete: {len(all_docs)} total documents")
        return all_docs

    def fetch_all_documents(self) -> list[Document]:
        """Fetch documents from all enabled sources (synchronous wrapper).
        
        Returns:
            List of all fetched documents
        """
        try:
            # Try to get existing event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is already running, create a new one in a thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.fetch_all_documents_async())
                    return future.result()
            else:
                return loop.run_until_complete(self.fetch_all_documents_async())
        except RuntimeError:
            # No event loop, create a new one
            return asyncio.run(self.fetch_all_documents_async())

    def chunk_documents(self, documents: list[Document]) -> list[Document]:
        """Split documents into chunks with per-source chunk_size/overlap and enhanced metadata."""
        chunks: list[Document] = []
        by_source: dict[str, list[Document]] = {}
        for doc in documents:
            key = doc.metadata.get("source_name") or "_default"
            by_source.setdefault(key, []).append(doc)

        for source_name, docs in by_source.items():
            splitter = self._create_splitter(source_name if source_name != "_default" else None)
            for doc in docs:
                doc_chunks = splitter.split_documents([doc])
                for i, chunk in enumerate(doc_chunks):
                    chunk.metadata["chunk_index"] = i
                    chunk.metadata["total_chunks"] = len(doc_chunks)
                    chunk.metadata["parent_doc_id"] = hash(doc.page_content)
                chunks.extend(doc_chunks)
        return chunks

    def refresh_knowledge_base(self) -> dict[str, int]:
        """Execute full knowledge base refresh.
        
        Returns:
            Dictionary with refresh statistics
        """
        logger.info("=== Knowledge base refresh started ===")
        
        # Fetch all documents
        all_docs = self.fetch_all_documents()
        
        if not all_docs:
            logger.error("No documents retrieved, skipping refresh")
            return {"documents": 0, "chunks": 0}
        
        # Chunk documents
        chunks = self.chunk_documents(all_docs)
        
        logger.info(f"Documents: {len(all_docs)}, Chunks: {len(chunks)}")
        
        # Use uncached embeddings so refresh does not write to Redis
        vectordb = self._get_vectordb(use_embedding_cache=False)
        
        # Full rebuild (delete and recreate)
        try:
            vectordb.delete_collection()
            logger.info("Deleted existing collection")
        except Exception as e:
            logger.warning(f"Could not delete collection (may not exist): {e}")
        
        vectordb = self._get_vectordb(use_embedding_cache=False)
        vectordb.add_documents(chunks)
        
        logger.info(f"=== Knowledge base refresh complete: {len(chunks)} chunks written ===")
        
        return {
            "documents": len(all_docs),
            "chunks": len(chunks),
        }
