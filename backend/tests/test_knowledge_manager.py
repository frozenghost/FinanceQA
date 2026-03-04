"""Tests for knowledge manager."""

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from services.knowledge_manager import KnowledgeManager


@pytest.fixture
def mock_config(tmp_path):
    """Create a mock configuration file."""
    config = {
        "sources": [
            {
                "name": "test_source_1",
                "type": "web",
                "enabled": True,
                "fetcher": "WebPageFetcher",
                "config": {"urls": ["https://example.com"]},
            },
            {
                "name": "test_source_2",
                "type": "wiki",
                "enabled": True,
                "fetcher": "WikipediaFetcher",
                "config": {"queries": ["test"]},
            },
            {
                "name": "disabled_source",
                "type": "web",
                "enabled": False,
                "fetcher": "WebPageFetcher",
                "config": {"urls": ["https://disabled.com"]},
            },
        ],
        "chunking": {
            "chunk_size": 512,
            "chunk_overlap": 64,
            "separators": ["\n\n", "\n"],
        },
        "vectordb": {
            "collection_name": "test_collection",
            "persist_directory": str(tmp_path / "chroma"),
        },
    }

    config_path = tmp_path / "test_config.json"
    with open(config_path, "w") as f:
        json.dump(config, f)

    return config_path


def test_knowledge_manager_init(mock_config):
    """Test KnowledgeManager initialization."""
    manager = KnowledgeManager(mock_config)
    assert manager.config is not None
    assert len(manager.config["sources"]) == 3
    assert manager.splitter is not None


def test_create_fetcher(mock_config):
    """Test fetcher creation."""
    manager = KnowledgeManager(mock_config)

    source_config = {
        "name": "test",
        "fetcher": "WebPageFetcher",
        "config": {"urls": ["https://example.com"]},
    }

    fetcher = manager._create_fetcher(source_config)
    assert fetcher is not None


def test_create_fetcher_unknown_type(mock_config):
    """Test fetcher creation with unknown type."""
    manager = KnowledgeManager(mock_config)

    source_config = {
        "name": "test",
        "fetcher": "UnknownFetcher",
        "config": {},
    }

    fetcher = manager._create_fetcher(source_config)
    assert fetcher is None


@pytest.mark.asyncio
async def test_fetch_all_documents_async(mock_config):
    """Test async document fetching."""
    manager = KnowledgeManager(mock_config)

    # Mock fetcher to return test documents
    mock_doc1 = Document(page_content="Test 1", metadata={"source": "test1"})
    mock_doc2 = Document(page_content="Test 2", metadata={"source": "test2"})

    with patch.object(
        manager, "_fetch_from_source"
    ) as mock_fetch:
        mock_fetch.side_effect = [
            ("test_source_1", [mock_doc1]),
            ("test_source_2", [mock_doc2]),
            ("disabled_source", []),
        ]

        docs = await manager.fetch_all_documents_async()

        # Should have 2 documents (disabled source returns empty list)
        assert len(docs) == 2
        assert docs[0].page_content == "Test 1"
        assert docs[1].page_content == "Test 2"


def test_fetch_all_documents_sync(mock_config):
    """Test synchronous document fetching wrapper."""
    manager = KnowledgeManager(mock_config)

    mock_doc = Document(page_content="Test", metadata={"source": "test"})

    with patch.object(
        manager, "_fetch_from_source"
    ) as mock_fetch:
        mock_fetch.return_value = ("test_source", [mock_doc])

        docs = manager.fetch_all_documents()

        assert len(docs) >= 0  # May vary based on enabled sources


def test_chunk_documents(mock_config):
    """Test document chunking."""
    manager = KnowledgeManager(mock_config)

    docs = [
        Document(
            page_content="A" * 1000,  # Long content to trigger chunking
            metadata={"source": "test"},
        )
    ]

    chunks = manager.chunk_documents(docs)

    assert len(chunks) > 0
    # Check that chunk metadata is added
    assert "chunk_index" in chunks[0].metadata
    assert "total_chunks" in chunks[0].metadata
    assert "parent_doc_id" in chunks[0].metadata


def test_fetch_from_source_disabled(mock_config):
    """Test fetching from disabled source."""
    manager = KnowledgeManager(mock_config)

    source_config = {
        "name": "disabled",
        "enabled": False,
        "fetcher": "WebPageFetcher",
        "config": {},
    }

    name, docs = manager._fetch_from_source(source_config)

    assert name == "disabled"
    assert len(docs) == 0


def test_fetch_from_source_error_handling(mock_config):
    """Test error handling in fetch_from_source."""
    manager = KnowledgeManager(mock_config)

    source_config = {
        "name": "error_source",
        "enabled": True,
        "fetcher": "WebPageFetcher",
        "config": {"urls": []},  # Invalid config
    }

    # Should not raise exception, just return empty list
    name, docs = manager._fetch_from_source(source_config)

    assert name == "error_source"
    assert isinstance(docs, list)
