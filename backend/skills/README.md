# Skills Architecture

Professional skill organization inspired by Anthropic's financial-services-plugins.

## Skill Modules

### 1. market_data
Real-time quotes and historical price data.

**Tools:**
- `get_real_time_quote(ticker)` - Current price, day performance, 52-week range
- `get_historical_prices(ticker, period, interval)` - OHLCV data for charting

**Use cases:** Price checks, chart data, intraday performance

---

### 2. fundamentals
Company financials, valuation metrics, and earnings.

**Tools:**
- `get_company_fundamentals(ticker)` - P/E, P/B, ROE, margins, debt ratios
- `get_earnings_history(ticker)` - Quarterly and annual earnings trends

**Use cases:** Valuation analysis, financial health assessment, earnings review

---

### 3. technical_analysis
Technical indicators and trading signals.

**Tools:**
- `calculate_technical_indicators(ticker, period)` - MA, RSI, MACD, Stochastic, ATR

**Use cases:** Trend analysis, momentum signals, overbought/oversold detection

---

### 4. news
Financial news and market sentiment.

**Tools:**
- `get_financial_news(query, page_size)` - Latest news articles from NewsAPI

**Use cases:** Market updates, company announcements, sector news

---

### 5. research
Knowledge base search and web research.

**Tools:**
- `search_knowledge_base(query, top_k)` - Hybrid retrieval (vector + BM25 + rerank)
- `search_web(query, max_results)` - Real-time web search via Tavily

**Use cases:** Financial concepts, definitions, latest information

---

## Design Principles

1. **Separation of Concerns**: Each skill has a clear, focused purpose
2. **No Redundancy**: Eliminated overlap between market_data and technical_metrics
3. **Professional Naming**: Clear, descriptive tool names following industry standards
4. **Composability**: Tools can be combined for complex analysis workflows

## Migration from v2.2

| Old Tool | New Tool(s) |
|----------|-------------|
| `get_market_data` | `get_real_time_quote` + `get_historical_prices` |
| `get_technical_indicators` | `calculate_technical_indicators` |
| `search_knowledge_base` (rag_search) | `search_knowledge_base` (research) |
| `search_web` (web_search) | `search_web` (research) |
| N/A | `get_company_fundamentals` (new) |
| N/A | `get_earnings_history` (new) |

## Total: 8 Tools across 5 Skill Modules
