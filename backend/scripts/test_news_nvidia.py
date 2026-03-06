"""Test news skill with 'Latest news about NVIDIA' and verify result count."""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    from skills.news.tool import get_financial_news

    query = "Latest news about NVIDIA"
    page_size = 10

    logger.info("Calling get_financial_news(query=%r, page_size=%s)", query, page_size)
    result = await get_financial_news.ainvoke({"query": query, "page_size": page_size})

    if "error" in result:
        logger.error("Tool returned error: %s", result["error"])
        return 1

    articles = result.get("articles", [])
    total = result.get("total_results", 0)
    sources = result.get("data_sources", [])

    logger.info("Result: total_results=%d, data_sources=%s", total, sources)
    for i, a in enumerate(articles, 1):
        logger.info("  [%d] %s | %s", i, a.get("title", "")[:60], a.get("source", ""))

    if total < 2:
        logger.warning("Expected at least 2 articles for '%s', got %d", query, total)
        return 1
    logger.info("OK: got %d articles", total)
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
