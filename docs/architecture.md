# Finance QA — Architecture

## High-level: Frontend ↔ Backend ↔ External

```mermaid
flowchart TB
    subgraph Client["Client"]
        UI[React + Vite\nTanStack Router]
    end

    subgraph Backend["Backend (FastAPI)"]
        API[API Layer]
        Agent[LangGraph Agent]
        Svc[Services]
        Skills[Skills / Tools]
        API --> Agent
        API --> Skills
        Agent --> Svc
        Agent --> Skills
        Skills --> Svc
    end

    subgraph External["External"]
        OpenRouter[OpenRouter\nLLM + Embedding]
        Redis[(Redis\nCache)]
        Chroma[(Chroma\nVector DB)]
        Yahoo[yfinance]
        Tavily[Tavily API]
    end

    UI -->|"POST /api/query (SSE)"| API
    UI -->|"GET /api/market/:ticker"| API
    UI -->|"POST /admin/refresh-knowledge"| API

    Svc --> OpenRouter
    Svc --> Redis
    Skills --> Chroma
    Skills --> Yahoo
    Skills --> Tavily
    Svc --> Chroma
```

## Request flow: Query (SSE)

```mermaid
sequenceDiagram
    participant F as Frontend
    participant Q as POST /api/query
    participant G as LangGraph Agent
    participant C as Coordinator (optional)
    participant T as Tools
    participant Ext as OpenRouter / Redis / Chroma / yfinance / Tavily

    F->>Q: message + history
    Q->>G: astream_events(messages)
    alt USE_COORDINATOR
        G->>C: coordinator_node
        C->>Ext: LLM (routing, plan)
        C-->>Q: thinking_complete (markdown)
        G->>T: ToolNode (parallel)
    else ReAct only
        G->>T: create_react_agent tools
    end
    T->>Ext: get_real_time_quote, get_historical_prices, get_company_fundamentals, get_earnings_history, calculate_technical_indicators, get_financial_news, search_knowledge_base, search_web
    Ext-->>T: results
    T-->>G: tool messages
    G->>Ext: LLM (answer)
    G-->>Q: answer tokens (stream)
    Q-->>F: SSE: answer, step, step_complete, metadata, done
```

## Backend components

```mermaid
flowchart LR
    subgraph API["api/routes"]
        Query["/api/query\nSSE stream"]
        Market["/api/market/:ticker"]
        Admin["/admin/refresh-knowledge\n/admin/evaluate-models\n/admin/health"]
    end

    subgraph Core["core/agent"]
        Graph[graph.py\nReAct or Coordinator]
        State[state.py]
        Coord[coordinator.py]
        Graph --> State
        Graph --> Coord
    end

    subgraph Services["services"]
        LLM[llm_client\nOpenRouter]
        Emb[embedding\n+ Redis cache]
        Cache[cache_service\nRedis]
        KM[knowledge_manager\nChroma + fetchers]
        Fetchers[fetchers\nWeb, Wiki, Yahoo, Tavily, Local]
        KM --> Fetchers
    end

    subgraph Skills["skills"]
        MD[market_data]
        Fd[fundamentals]
        TA[technical_analysis]
        News[news]
        Res[research\nKB + web]
    end

    Query --> Graph
    Market --> MD
    Admin --> KM
    Graph --> LLM
    Graph --> Skills
    MD --> Cache
    Fd --> Yahoo
    TA --> Yahoo
    News --> Tavily
    Res --> Emb
    Res --> Chroma
    Res --> Tavily
```

## Data & scheduler

- **Knowledge base refresh**: APScheduler (lifespan) runs daily (+ Monday extra); config in `backend/config/knowledge_sources.json`. Fetchers → embed → Chroma.
- **Redis**: Cache for market data, news, embeddings (when available; fail-open if Redis down).
- **Chroma**: Vector store for RAG; used by `search_knowledge_base` and by `knowledge_manager` when refreshing.
