# Finance QA System

LangGraph + RAG–based financial Q&A: market data, fundamentals, technical indicators, news, and knowledge base / web search.

## Quick Start

**Requirements:** Python 3.12+, Node.js 18+ (Bun recommended), Docker, Redis

```bash
git clone <repository-url>
cd FinanceQA
cp .env.example .env   # Set OPENAI_API_KEY or OPENROUTER_API_KEY; optional: TAVILY_API_KEY, NEWS_API_KEY
```

**Docker (recommended)**

```bash
docker-compose up -d
# Frontend http://localhost:5173  Backend http://localhost:8000  API docs http://localhost:8000/docs
```

**Local development**

```bash
# Backend
cd backend && uv sync && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend && bun install && bun run dev
```

## Features

- **Agent tools:** Real-time quotes and history, company fundamentals/earnings, technical indicators (MA, RSI, MACD, etc.), financial news, knowledge base search, web search (Tavily)
- **Knowledge base:** Configure `backend/config/knowledge_sources.json`; supports web pages, Wikipedia, Yahoo Finance, local files, Tavily; scheduled refresh (daily + extra on Monday)
- **Helper scripts:** `make help` / `.\commands.ps1 help` (start, stop, kb-refresh, logs)

## Commands

| Use case | Command |
|----------|---------|
| Backend dev / test / format | From `backend`: `uv run uvicorn main:app --reload`, `uv run pytest`, `uv run ruff format .`, `uv run ruff check .` |
| Knowledge base | `uv run python scripts/refresh_knowledge.py --run-now`, `uv run python scripts/test_fetchers.py` |
| Reranker model | `uv run --with optimum --with torch python scripts/download_reranker.py` |
| Frontend | `bun run dev` / `bun run build` / `bun run lint` |
| Docker | `docker-compose up -d`, `docker-compose logs -f`, `docker-compose down` |

## Project Structure

```
backend/
├── api/              # FastAPI routes
├── config/           # settings, knowledge_sources.json
├── core/agent/       # LangGraph Agent
├── services/         # embedding, cache, llm, knowledge_manager, fetchers
├── skills/           # market_data, fundamentals, technical_analysis, news, research
├── scripts/          # refresh_knowledge, test_fetchers, download_reranker, evaluate_model
├── main.py
frontend/             # React + Vite
docker-compose.yml, .env.example
```

## Configuring the Knowledge Base

Edit `backend/config/knowledge_sources.json` to add or remove sources, then run `uv run python scripts/test_fetchers.py` to verify and `uv run python scripts/refresh_knowledge.py --run-now` to refresh.

## Testing

```bash
cd backend && uv run pytest
cd frontend && bun test
```

## Troubleshooting

- **Backend won’t start:** Check Python 3.12+, `.env`, Redis (`docker-compose ps redis`)
- **Empty knowledge base:** Check `knowledge_sources.json`, run `test_fetchers.py`, then `refresh_knowledge.py --run-now`
- **Frontend can’t reach backend:** `curl http://localhost:8000/health`, check CORS and browser console

## Deployment & env vars

Production: `docker-compose up -d`. Required: `OPENAI_API_KEY` or `OPENROUTER_API_KEY`. Optional: `TAVILY_API_KEY`, `NEWS_API_KEY`, `REDIS_URL`; see `.env.example` for knowledge-base options.

## Docs & License

- [Architecture](docs/architecture.md) — frontend/backend/external diagram and request flow
- [Development plan](development-plan-v2.2.md)
- [LangGraph](https://langchain-ai.github.io/langgraph/) · [FastAPI](https://fastapi.tiangolo.com/) · [uv](https://docs.astral.sh/uv/)

MIT License. Issues and PRs welcome.
