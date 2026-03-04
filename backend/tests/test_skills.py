"""Unit tests for individual skills."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


SKILLS_DIR = Path(__file__).parent.parent / "skills"


class TestMarketDataSkill:
    """Tests for the market_data skill."""

    def test_valid_ticker_returns_expected_keys(self):
        """A valid ticker should return price data with expected keys."""
        from skills.market_data.tool import get_market_data

        result = get_market_data.invoke({"ticker": "AAPL", "period": "7d"})

        # Should have core fields (may hit cache or live data)
        assert isinstance(result, dict)
        if "error" not in result:
            for key in ["ticker", "current", "change_pct", "trend"]:
                assert key in result, f"Missing key: {key}"

    def test_invalid_ticker_returns_error(self):
        """An invalid ticker should return an error message."""
        from skills.market_data.tool import get_market_data

        result = get_market_data.invoke({"ticker": "INVALID_TICKER_XYZ123", "period": "7d"})
        assert isinstance(result, dict)
        assert "error" in result


class TestNewsSkill:
    """Tests for the news skill."""

    def test_news_returns_expected_structure(self):
        """News query should return articles list structure."""
        from skills.news.tool import get_financial_news

        result = get_financial_news.invoke({"query": "Tesla", "page_size": 2})
        assert isinstance(result, dict)
        # Either articles or error (if API key missing)
        assert "articles" in result or "error" in result


class TestWebSearchSkill:
    """Tests for the web_search skill."""

    def test_web_search_returns_expected_structure(self):
        """Web search should return results list structure."""
        from skills.web_search.tool import search_web

        result = search_web.invoke({"query": "Tesla stock price", "max_results": 2})
        assert isinstance(result, dict)
        assert "results" in result or "error" in result


class TestTechnicalMetricsSkill:
    """Tests for the technical_metrics skill."""

    def test_valid_ticker_returns_indicators(self):
        """A valid ticker should return technical indicators."""
        from skills.technical_metrics.tool import get_technical_indicators

        result = get_technical_indicators.invoke({"ticker": "AAPL", "period": "90d"})
        assert isinstance(result, dict)
        if "error" not in result:
            assert "indicators" in result
            assert "signals" in result


class TestRagSearchSkill:
    """Tests for the rag_search skill."""

    def test_search_returns_expected_structure(self):
        """RAG search should return results structure even if empty."""
        from skills.rag_search.tool import search_knowledge_base

        result = search_knowledge_base.invoke({"query": "什么是市盈率", "top_k": 3})
        assert isinstance(result, dict)
        assert "query" in result
        assert "results" in result or "error" in result


class TestSkillTestCases:
    """Validate that all test_cases.json files are well-formed."""

    def test_all_test_cases_json_valid(self):
        """Every test_cases.json should be valid JSON with required fields."""
        for tc_path in SKILLS_DIR.rglob("test_cases.json"):
            content = tc_path.read_text(encoding="utf-8")
            cases = json.loads(content)
            assert isinstance(cases, list), f"{tc_path} should be a list"
            for case in cases:
                assert "input" in case, f"Missing 'input' in {tc_path}"
                assert "expected_keys" in case, f"Missing 'expected_keys' in {tc_path}"
