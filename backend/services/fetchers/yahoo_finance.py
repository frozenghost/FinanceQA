"""Yahoo Finance fetcher for company earnings data."""

import logging
from typing import Any

import yfinance as yf
from langchain_core.documents import Document

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class YahooFinanceFetcher(BaseFetcher):
    """Fetcher for Yahoo Finance company data."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.tickers = config.get("tickers", [])
        self.data_fields = config.get("data_fields", [
            "trailingPE", "priceToBook", "trailingEps", "totalRevenue",
            "profitMargins", "returnOnEquity", "industry"
        ])

    def validate_config(self) -> bool:
        if not self.tickers:
            logger.error("YahooFinanceFetcher: No tickers configured")
            return False
        return True

    def fetch(self) -> list[Document]:
        """Fetch financial data from Yahoo Finance."""
        if not self.validate_config():
            return []

        docs: list[Document] = []
        for ticker in self.tickers:
            try:
                info = yf.Ticker(ticker).info
                
                # Build formatted text content
                lines = [f"# {ticker} 财务摘要（来源：Yahoo Finance）"]
                field_mapping = {
                    "trailingPE": "市盈率（P/E）",
                    "priceToBook": "市净率（P/B）",
                    "trailingEps": "EPS",
                    "totalRevenue": "营收（TTM）",
                    "profitMargins": "净利润率",
                    "returnOnEquity": "ROE",
                    "industry": "行业"
                }
                
                for field in self.data_fields:
                    label = field_mapping.get(field, field)
                    value = info.get(field, "N/A")
                    lines.append(f"{label}: {value}")
                
                text = "\n".join(lines)
                
                doc = Document(
                    page_content=text,
                    metadata={
                        "source": f"yfinance:{ticker}",
                        "type": "earnings",
                        "fetcher": "YahooFinanceFetcher",
                        "ticker": ticker,
                        "company_name": info.get("longName", ticker)
                    }
                )
                docs.append(doc)
                logger.info(f"Loaded earnings data: {ticker}")
            except Exception as e:
                logger.error(f"Yahoo Finance fetch failed for {ticker}: {e}")

        return docs
