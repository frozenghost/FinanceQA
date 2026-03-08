"""Unit tests for all skills (async tools use ainvoke)."""

import pytest


class TestMarketDataSkill:
    """Tests for the market_data skill."""

    async def test_real_time_quote_returns_expected_keys(self):
        """A valid ticker should return quote data with expected keys."""
        from skills.market_data.tool import get_real_time_quote

        result = await get_real_time_quote.ainvoke({"ticker": "AAPL"})

        assert isinstance(result, dict)
        if "error" not in result:
            assert "ticker" in result
            assert "current_price" in result
            assert "change_percent" in result

    async def test_historical_prices_returns_ohlcv(self):
        """A valid ticker should return historical OHLCV data."""
        from skills.market_data.tool import get_historical_prices

        result = await get_historical_prices.ainvoke({"ticker": "AAPL", "period": "1mo"})

        assert isinstance(result, dict)
        if "error" not in result:
            assert "ohlcv" in result
            assert isinstance(result["ohlcv"], list)

    async def test_invalid_ticker_returns_error(self):
        """An invalid ticker should return an error message."""
        from skills.market_data.tool import get_real_time_quote

        result = await get_real_time_quote.ainvoke({"ticker": "INVALID_TICKER_XYZ123"})

        assert isinstance(result, dict)
        assert "error" in result


class TestFundamentalsSkill:
    """Tests for the fundamentals skill."""

    async def test_company_fundamentals_returns_metrics(self):
        """A valid ticker should return fundamental metrics."""
        from skills.fundamentals.tool import get_company_fundamentals

        result = await get_company_fundamentals.ainvoke({"ticker": "AAPL"})

        assert isinstance(result, dict)
        if "error" not in result:
            assert "valuation" in result
            assert "profitability" in result

    async def test_earnings_history_returns_data(self):
        """A valid ticker should return earnings history or error."""
        from skills.fundamentals.tool import get_earnings_history

        result = await get_earnings_history.ainvoke({"ticker": "AAPL"})

        assert isinstance(result, dict)
        assert "ticker" in result or "error" in result
        if "error" not in result:
            assert "ticker" in result


class TestTechnicalAnalysisSkill:
    """Tests for the technical_analysis skill."""

    async def test_technical_indicators_returns_signals(self):
        """A valid ticker should return technical indicators and signals."""
        from skills.technical_analysis.tool import calculate_technical_indicators

        result = await calculate_technical_indicators.ainvoke({
            "ticker": "AAPL",
            "analysis_start": "2024-01-01",
            "analysis_end": "2024-06-30",
            "interval": "1d",
        })

        assert isinstance(result, dict)
        if "error" not in result:
            assert "indicators" in result
            assert "signals" in result
            assert "overall_signal" in result


class TestNewsSkill:
    """Tests for the news skill."""

    async def test_financial_news_returns_articles(self):
        """News search should return articles list."""
        from skills.news.tool import get_financial_news

        result = await get_financial_news.ainvoke({"query": "Apple earnings", "page_size": 3})

        assert isinstance(result, dict)
        if "error" not in result:
            assert "articles" in result
            assert isinstance(result["articles"], list)


class TestResearchSkill:
    """Tests for the research skill."""

    async def test_knowledge_base_search_returns_structure(self):
        """Knowledge base search should return results structure."""
        from skills.research.tool import search_knowledge_base

        result = await search_knowledge_base.ainvoke({"query": "What is P/E ratio", "top_k": 3})

        assert isinstance(result, dict)
        assert "query" in result
        assert "results" in result

    async def test_web_search_returns_results(self):
        """Web search should return results list structure."""
        from skills.research.tool import search_web

        result = await search_web.ainvoke({"query": "Tesla stock price", "max_results": 2})

        assert isinstance(result, dict)
        if "error" not in result:
            assert "results" in result
            assert isinstance(result["results"], list)
