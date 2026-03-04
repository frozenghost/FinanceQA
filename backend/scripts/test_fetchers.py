"""Test script for knowledge base fetchers.

Usage:
    uv run python scripts/test_fetchers.py [fetcher_name]
    
Examples:
    uv run python scripts/test_fetchers.py                    # Test all fetchers
    uv run python scripts/test_fetchers.py WebPageFetcher     # Test specific fetcher
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.knowledge_manager import KnowledgeManager, FETCHER_REGISTRY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def test_single_fetcher(source_config: dict):
    """Test a single fetcher configuration."""
    source_name = source_config.get("name", "unknown")
    fetcher_name = source_config.get("fetcher", "unknown")
    
    print(f"\n{'='*60}")
    print(f"Testing: {source_name} ({fetcher_name})")
    print(f"{'='*60}")
    
    if not source_config.get("enabled", True):
        print(f"⚠️  Source is disabled, skipping")
        return
    
    manager = KnowledgeManager()
    fetcher = manager._create_fetcher(source_config)
    
    if not fetcher:
        print(f"❌ Failed to create fetcher")
        return
    
    try:
        docs = fetcher.fetch()
        print(f"✅ Successfully fetched {len(docs)} documents")
        
        if docs:
            print(f"\nSample document:")
            sample = docs[0]
            print(f"  Content length: {len(sample.page_content)} chars")
            print(f"  Metadata: {sample.metadata}")
            print(f"  Content preview: {sample.page_content[:200]}...")
    except Exception as e:
        print(f"❌ Fetch failed: {e}")
        logger.exception("Detailed error:")


def test_all_fetchers():
    """Test all configured fetchers."""
    manager = KnowledgeManager()
    sources = manager.config.get("sources", [])
    
    print(f"\n{'='*60}")
    print(f"Testing {len(sources)} configured sources")
    print(f"{'='*60}")
    
    for source_config in sources:
        test_single_fetcher(source_config)
    
    print(f"\n{'='*60}")
    print("Testing complete")
    print(f"{'='*60}")


def test_by_fetcher_name(fetcher_name: str):
    """Test all sources using a specific fetcher."""
    manager = KnowledgeManager()
    sources = manager.config.get("sources", [])
    
    matching_sources = [
        s for s in sources 
        if s.get("fetcher") == fetcher_name
    ]
    
    if not matching_sources:
        print(f"❌ No sources found using fetcher: {fetcher_name}")
        print(f"\nAvailable fetchers: {', '.join(FETCHER_REGISTRY.keys())}")
        return
    
    print(f"\nFound {len(matching_sources)} source(s) using {fetcher_name}")
    
    for source_config in matching_sources:
        test_single_fetcher(source_config)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test knowledge base fetchers")
    parser.add_argument(
        "fetcher",
        nargs="?",
        help="Specific fetcher name to test (e.g., WebPageFetcher)"
    )
    
    args = parser.parse_args()
    
    if args.fetcher:
        test_by_fetcher_name(args.fetcher)
    else:
        test_all_fetchers()
