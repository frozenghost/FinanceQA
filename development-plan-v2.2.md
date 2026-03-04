# 金融资产问答系统 · 开发计划 v2.3

> **核心调整**：轻前端 / 重后端 · LangGraph Skills · 定时知识库刷新 · OpenRouter 多模型路由  
> **新增需求**：本地文件知识库加载（txt/md/docx/pdf） · 模型替换质量评估框架  
> **工具链**：Python 用 `uv` 管理 · 前端用 `bun` + TanStack · 替换 Next.js 为 Vite SPA  
> **总工期**：5 + 1 个工作日（额外 1 天用于新增需求）  
> **技术原则**：优先三方库，最小化自研，后端逻辑集中，前端仅做展示层

---

## 目录

1. [架构调整概览](#1-架构调整概览)
2. [工程工具链](#2-工程工具链)
   - [2.1 后端：uv 包管理](#21-后端uv-包管理)
   - [2.2 前端：bun + TanStack + Vite](#22-前端bun--tanstack--vite)
3. [后端核心设计（重点）](#3-后端核心设计重点)
   - [3.1 OpenRouter 多模型支持](#31-openrouter-多模型支持)
   - [3.2 LangGraph ReAct Agent + Skills](#32-langgraph-react-agent--skills)
   - [3.3 Redis 缓存层](#33-redis-缓存层)
   - [3.4 知识库定时刷新脚本](#34-知识库定时刷新脚本)
   - [3.5 本地文件知识库加载（新增）](#35-本地文件知识库加载新增)
   - [3.6 模型质量评估框架（新增）](#36-模型质量评估框架新增)
4. [前端设计（轻量）](#4-前端设计轻量)
5. [项目目录结构](#5-项目目录结构)
6. [分阶段开发计划](#6-分阶段开发计划)
7. [三方库选型清单](#7-三方库选型清单)
8. [环境配置与启动](#8-环境配置与启动)

---

## 1. 架构调整概览

### 设计原则变化

| 维度 | v2.1 | v2.2（本版本） |
|------|------|----------------|
| Python 包管理 | pip / poetry | **uv**（极速，锁文件，虚拟环境一体化） |
| 前端框架 | Next.js 14 | **Vite + React**（轻量 SPA，无 SSR 负担） |
| 前端路由 | Next.js App Router | **TanStack Router**（类型安全，文件路由） |
| 前端数据请求 | Vercel AI SDK `useChat` | **TanStack Query** + 自定义 SSE hook |
| 前端包管理 | npm | **bun**（安装速度快 10-25x，内置 test runner） |
| LLM 接入 | 单一 OpenAI SDK | OpenRouter 统一网关，多模型切换 |
| 知识库维护 | 手动入库 | 定时刷新脚本（APScheduler） |
| 知识库来源 | 仅在线数据源 | **在线 + 本地文件**（txt/md/docx/pdf）★ 新增 |
| 模型质量管理 | 无 | **标准评估框架 + 对比报告** ★ 新增 |

### 整体架构

```
┌────────────────────────────────────────────────────────┐
│              轻量前端（Vite + React SPA）                │
│                                                         │
│  TanStack Router  →  页面路由                           │
│  TanStack Query   →  数据获取 + 缓存 + 状态同步         │
│  自定义 useSSE    →  流式输出（EventSource）             │
│  Recharts         →  行情走势图                          │
└────────────────────────────┬───────────────────────────┘
                             │ HTTP + SSE
┌────────────────────────────▼───────────────────────────┐
│                  FastAPI 后端（重点）                    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │           LangGraph ReAct Agent                 │   │
│  │  (create_react_agent · prebuilt)                │   │
│  │                                                  │   │
│  │  Skills:                                         │   │
│  │  ├── market_data   → yfinance                   │   │
│  │  ├── news          → NewsAPI                    │   │
│  │  ├── rag_search    → ChromaDB Hybrid            │   │
│  │  ├── web_search    → Tavily                     │   │
│  │  └── tech_metrics  → pandas-ta                  │   │
│  └─────────────────────────────────────────────────┘   │
│                         │                               │
│  ┌──────────────────────▼──────────────────────────┐   │
│  │   OpenRouter LLM 网关（openai SDK · base_url）   │   │
│  │   claude-3.5-sonnet / gpt-4o / mistral / llama  │   │
│  └─────────────────────────────────────────────────┘   │
│                         │                               │
│  ┌──────────────────────▼──────────────────────────┐   │
│  │         Redis 缓存层（TTL 分级策略）             │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │  APScheduler 定时任务                             │  │
│  │  每日 02:00  全量刷新金融知识库                   │  │
│  │  ★ 含本地文件扫描（txt/md/docx/pdf）             │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │  ★ 模型质量评估框架                               │  │
│  │  标准数据集 → 多模型测试 → 裁判评分 → 对比报告   │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
         │               │              │           │
    yfinance         ChromaDB       SQLite     本地文件
    NewsAPI          (向量库)       (刷新日志)  (知识文档)
    Tavily
```

---

## 2. 工程工具链

### 2.1 后端：uv 包管理

`uv` 是 Astral 出品的极速 Python 包管理器，兼容 pip 生态，同时提供虚拟环境、锁文件、脚本运行的一体化体验。

#### 项目初始化

```bash
# 安装 uv（一次性）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 初始化后端项目
cd backend
uv init --python 3.12        # 生成 pyproject.toml

# 添加依赖（等价于 pip install，但会写入 pyproject.toml + uv.lock）
uv add fastapi uvicorn[standard]
uv add langgraph langchain-core langchain-community langchain-openai langchain-chroma
uv add openai                # OpenRouter 复用此 SDK
uv add yfinance pandas pandas-ta
uv add redis apscheduler
uv add tavily-python newsapi-python
uv add rank-bm25 onnxruntime optimum transformers numpy
uv add pydantic-settings
uv add aiosqlite              # SQLite 异步驱动，刷新日志用

# 开发依赖（测试 + 格式化）
uv add --dev pytest pytest-asyncio httpx ruff mypy
```

#### pyproject.toml 结构

```toml
# backend/pyproject.toml

[project]
name = "finance-qa-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "langgraph>=0.2",
    "langchain-core>=0.3",
    "langchain-community>=0.3",
    "langchain-openai>=0.2",
    "langchain-chroma>=0.1",
    "openai>=1.50",
    "yfinance>=0.2",
    "pandas>=2.2",
    "pandas-ta>=0.3",
    "redis>=5.0",
    "apscheduler>=3.10",
    "tavily-python>=0.5",
    "newsapi-python>=0.2",
    "rank-bm25>=0.2",
    "onnxruntime>=1.17",
    "optimum>=1.19",
    "transformers>=4.40",
    "numpy>=1.26",
    "pydantic-settings>=2.5",
    "aiosqlite>=0.20",
]

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",
    "ruff>=0.7",
    "mypy>=1.12",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

#### 常用命令速查

```bash
uv run uvicorn main:app --reload          # 启动开发服务器
uv run pytest                             # 跑测试
uv run python scripts/refresh_knowledge.py --run-now   # 手动触发知识库刷新
uv run ruff check .                       # lint
uv sync                                   # 根据 uv.lock 同步依赖（CI/CD用）
uv add <pkg>                              # 添加依赖
uv remove <pkg>                           # 移除依赖
uv lock --upgrade                         # 升级所有依赖到最新兼容版本
```

> `uv run` 自动激活 `.venv`，无需手动 `source .venv/bin/activate`。CI 环境直接 `uv sync && uv run pytest` 即可。

---

### 2.2 前端：bun + TanStack + Vite

放弃 Next.js 的原因：本项目前端无 SEO 需求、无 SSR 需求、无 API Route 需求，Next.js 的编译时间和包体积对纯展示层是纯开销。Vite SPA 冷启动 < 300ms，构建产物更小。

#### 项目初始化

```bash
# 安装 bun（一次性）
curl -fsSL https://bun.sh/install | bash

# 创建 Vite + React + TypeScript 项目
cd frontend
bun create vite . --template react-ts

# 安装依赖
bun add @tanstack/react-router @tanstack/react-query
bun add @tanstack/react-router-devtools @tanstack/react-query-devtools
bun add recharts
bun add react-markdown remark-gfm
bun add tailwindcss @tailwindcss/vite        # Tailwind v4（Vite 插件版，零配置）
bun add clsx lucide-react

# 开发依赖
bun add -d @types/react @types/react-dom typescript vite
```

#### package.json scripts

```json
{
  "scripts": {
    "dev":     "vite",
    "build":   "tsc -b && vite build",
    "preview": "vite preview",
    "lint":    "tsc --noEmit",
    "test":    "bun test"
  }
}
```

#### TanStack Router 路由结构

```
src/routes/
├── __root.tsx          # 根布局（Header + QueryClientProvider）
├── index.tsx           # / → Chat 主界面
└── history.tsx         # /history → 历史会话（可选）
```

```typescript
// src/routes/__root.tsx
import { createRootRoute, Outlet } from "@tanstack/react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient();

export const Route = createRootRoute({
  component: () => (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-slate-950 text-white">
        <Outlet />
      </div>
    </QueryClientProvider>
  ),
});
```

#### TanStack Query：行情数据请求

```typescript
// src/hooks/useMarketData.ts
import { useQuery } from "@tanstack/react-query";

interface MarketData {
  ticker: string;
  current: number;
  change_pct: number;
  trend: "上涨" | "下跌" | "震荡";
  ohlcv: OHLCV[];
}

export function useMarketData(ticker: string, period = "7d") {
  return useQuery<MarketData>({
    queryKey: ["market", ticker, period],
    queryFn: () =>
      fetch(`/api/market/${ticker}?period=${period}`).then(r => r.json()),
    staleTime: 60_000,        // 1 分钟内不重复请求（配合后端 Redis 缓存）
    enabled: !!ticker,
  });
}
```

#### 自定义 SSE Hook（替代 Vercel AI SDK）

Vercel AI SDK 依赖 Next.js 环境，这里用原生 `EventSource` 实现，100 行以内搞定：

```typescript
// src/hooks/useSSEChat.ts
import { useState, useCallback, useRef } from "react";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  metadata?: {
    type: "market" | "rag" | "hybrid";
    ticker?: string;
    ohlcv?: OHLCV[];
    steps?: AgentStep[];   // ReAct 推理步骤，用于折叠展示
  };
}

export function useSSEChat() {
  const [messages, setMessages]   = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const abortRef                  = useRef<AbortController | null>(null);

  const send = useCallback(async (input: string) => {
    setIsLoading(true);
    abortRef.current = new AbortController();

    // 立即追加用户消息
    const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: input };
    setMessages(prev => [...prev, userMsg]);

    // 追加空的 assistant 消息，后续流式填充
    const assistantId = crypto.randomUUID();
    setMessages(prev => [...prev, { id: assistantId, role: "assistant", content: "" }]);

    try {
      const res = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: input,
          history: messages.slice(-10),   // 携带最近 10 条上下文
        }),
        signal: abortRef.current.signal,
      });

      const reader  = res.body!.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const lines = decoder.decode(value).split("\n");
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = JSON.parse(line.slice(6));

          if (data.type === "token") {
            // 流式追加文本 token
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId
                  ? { ...m, content: m.content + data.token }
                  : m
              )
            );
          } else if (data.type === "metadata") {
            // 行情数据、推理步骤等结构化 metadata
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId ? { ...m, metadata: data.payload } : m
              )
            );
          }
        }
      }
    } finally {
      setIsLoading(false);
    }
  }, [messages]);

  const stop = () => abortRef.current?.abort();

  return { messages, isLoading, send, stop };
}
```

---

## 3. 后端核心设计（重点）

### 3.1 OpenRouter 多模型支持

OpenRouter 提供统一的 OpenAI 兼容接口，无需修改代码即可切换底层模型。

#### 接入方式

```python
# services/llm_client.py
# 直接复用 openai SDK，仅替换 base_url

from openai import AsyncOpenAI
from langchain_openai import ChatOpenAI
from config.settings import settings
from config.models import MODEL_ROUTING

class LLMClient:
    def __init__(self):
        self._async_client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
        )

    def get_langchain_model(self, role: str = "market_analyst") -> ChatOpenAI:
        """返回 LangChain 兼容的 ChatOpenAI 实例，供 LangGraph Agent 使用"""
        model = MODEL_ROUTING.get(role, MODEL_ROUTING["market_analyst"])
        return ChatOpenAI(
            model=model,
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
            streaming=True,
            default_headers={
                "HTTP-Referer": settings.APP_URL,
                "X-Title": "Finance QA System",
            },
        )

    async def chat_raw(self, messages: list, model: str = None, stream: bool = True):
        """直接调用，用于 Router 分类等非 Agent 场景"""
        return await self._async_client.chat.completions.create(
            model=model or MODEL_ROUTING["router"],
            messages=messages,
            stream=stream,
        )
```

#### 模型路由配置

```python
# config/models.py

MODEL_ROUTING = {
    "router":         "openai/gpt-4o-mini",           # 分类任务，低延迟
    "market_analyst": "anthropic/claude-3.5-sonnet",  # 分析任务，推理强
    "rag_qa":         "openai/gpt-4o-mini",           # 有 context，中模型够
    # embedding 不走 OpenRouter，直接用 OpenAI
}

# 支持环境变量全局覆盖，演示时一行切换
# OVERRIDE_ALL_MODELS=mistralai/mistral-7b-instruct
```

#### 支持的模型（开箱即用）

```
anthropic/claude-3.5-sonnet       ← 推荐，分析能力强
openai/gpt-4o
openai/gpt-4o-mini                ← 低成本任务首选
mistralai/mistral-7b-instruct     ← 开源低成本
meta-llama/llama-3.1-8b-instruct
google/gemini-flash-1.5           ← 极速场景
```

---

### 3.2 LangGraph ReAct Agent + Skills

#### Skill 模块规范

每个 Skill 是一个独立目录，包含：

- `tool.py`：`@tool` 装饰器定义，含完整 docstring（LLM 通过 docstring 理解工具用途）
- `prompt.txt`：该工具的专项约束，合并进 System Prompt
- `test_cases.json`：输入/期望输出对，`uv run pytest` 自动验证

```
backend/skills/
├── __init__.py                # ALL_TOOLS = [market_data, news, rag_search, ...]
├── market_data/
│   ├── tool.py                # @tool + @cached(ttl=3600)
│   ├── prompt.txt
│   └── test_cases.json
├── news/
│   ├── tool.py
│   ├── prompt.txt
│   └── test_cases.json
├── rag_search/
│   ├── tool.py                # Hybrid BM25 + 向量 + Reranker
│   ├── prompt.txt             # 防幻觉约束
│   └── test_cases.json
├── web_search/
│   ├── tool.py                # Tavily
│   └── test_cases.json
└── technical_metrics/
    ├── tool.py                # pandas-ta: MA / RSI / MACD
    └── test_cases.json
```

#### Skill 实现示例

```python
# skills/market_data/tool.py

from langchain_core.tools import tool
from services.cache_service import cached
import yfinance as yf

@tool
@cached(key_prefix="market", ttl=3600)
def get_market_data(ticker: str, period: str = "7d") -> dict:
    """
    获取股票历史行情数据并计算涨跌幅与趋势。
    - ticker: 股票代码，如 BABA、TSLA、0700.HK
    - period: 时间范围，支持 1d / 7d / 30d / 90d / 1y
    返回当前价格、区间涨跌幅、最高/最低价、OHLCV 列表、趋势判断。
    注意：返回数据来自 Yahoo Finance，约有 15 分钟延迟。
    """
    tk   = yf.Ticker(ticker)
    hist = tk.history(period=period)

    if hist.empty:
        return {"error": f"未找到 {ticker} 的行情数据，请确认代码正确"}

    current    = hist["Close"].iloc[-1]
    start      = hist["Close"].iloc[0]
    change_pct = (current - start) / start * 100
    trend      = "上涨" if change_pct > 3 else ("下跌" if change_pct < -3 else "震荡")

    return {
        "ticker":      ticker,
        "current":     round(current, 2),
        "change_pct":  round(change_pct, 2),
        "high":        round(hist["High"].max(), 2),
        "low":         round(hist["Low"].min(), 2),
        "trend":       trend,
        "ohlcv":       hist[["Open","High","Low","Close","Volume"]]
                           .reset_index()
                           .to_dict("records"),
        "data_source": "yfinance",
        "delay_note":  "数据约有 15 分钟延迟",
    }
```

#### LangGraph Agent 图（最小化自研）

```python
# core/agent/graph.py

from langgraph.prebuilt import create_react_agent
from core.agent.state import AgentState
from services.llm_client import LLMClient
from skills import ALL_TOOLS
from prompts.loader import load_system_prompt

llm = LLMClient().get_langchain_model(role="market_analyst")

# ★ 使用 prebuilt，不手写节点和边
agent = create_react_agent(
    model=llm,
    tools=ALL_TOOLS,
    state_schema=AgentState,
    messages_modifier=load_system_prompt(),   # 合并所有 Skill prompt.txt
    # 内置递归上限，防止无限循环
    checkpointer=None,     # 无持久化，按需开启
)
```

```python
# core/agent/state.py

from langgraph.graph import MessagesState
from typing import Optional

class AgentState(MessagesState):
    ticker:     Optional[str] = None   # 解析出的股票代码
    query_type: Optional[str] = None   # market / rag / hybrid
    cache_hits: int           = 0      # 缓存命中计数（日志用）
```

```python
# prompts/loader.py — 合并 System Prompt + 各 Skill prompt.txt

from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"

def load_system_prompt() -> str:
    base = (Path(__file__).parent / "react_agent.txt").read_text()
    skill_prompts = []
    for p in SKILLS_DIR.rglob("prompt.txt"):
        skill_prompts.append(f"# {p.parent.name}\n{p.read_text()}")
    return base + "\n\n" + "\n\n".join(skill_prompts)
```

---

### 3.3 Redis 缓存层

#### 通用缓存装饰器

```python
# services/cache_service.py

import redis, json, hashlib, functools, logging
from config.settings import settings

logger = logging.getLogger(__name__)

try:
    _r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT,
                     decode_responses=True, socket_connect_timeout=2)
    _r.ping()
    REDIS_AVAILABLE = True
except Exception:
    logger.warning("Redis 不可用，缓存层已降级为直连模式")
    REDIS_AVAILABLE = False


def cached(key_prefix: str, ttl: int):
    """
    通用缓存装饰器。
    - Redis 可用时：命中返回缓存，未命中写入缓存
    - Redis 不可用时：直接透传，不影响主链路
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not REDIS_AVAILABLE:
                return func(*args, **kwargs)

            raw = json.dumps({"a": args, "k": kwargs}, sort_keys=True, default=str)
            key = f"{key_prefix}:{hashlib.md5(raw.encode()).hexdigest()[:12]}"

            try:
                if cached_val := _r.get(key):
                    result = json.loads(cached_val)
                    result["_cache"] = {"hit": True, "ttl": _r.ttl(key)}
                    return result
            except redis.RedisError as e:
                logger.warning(f"Cache read error: {e}")

            result = func(*args, **kwargs)

            try:
                _r.setex(key, ttl, json.dumps(result, default=str))
                result["_cache"] = {"hit": False}
            except redis.RedisError as e:
                logger.warning(f"Cache write error: {e}")

            return result
        return wrapper
    return decorator
```

#### TTL 策略

| 数据类型 | Cache Key 格式 | TTL | 原因 |
|----------|---------------|-----|------|
| 日线行情 OHLCV | `market:{hash}` | 3600s | 日线数据日内稳定 |
| 实时报价 | `quote:{ticker}` | 60s | 高频变化 |
| 新闻列表 | `news:{hash}` | 1800s | 时效性较强 |
| RAG Embedding | `emb:{hash}` | 86400s | 文本不变向量不变 |
| Web 搜索结果 | `web:{hash}` | 900s | 实时性最高 |
| 技术指标 | `ta:{hash}` | 3600s | 依赖历史数据，同参固定 |

---

### 3.4 知识库定时刷新脚本

```python
# scripts/refresh_knowledge.py

import logging, argparse
from pathlib import Path
import yfinance as yf
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_community.document_loaders import WebBaseLoader, WikipediaLoader
from langchain_core.documents import Document
from tavily import TavilyClient
from apscheduler.schedulers.background import BackgroundScheduler
from config.settings import settings

logger = logging.getLogger(__name__)

# ── 知识来源配置 ──────────────────────────────────────────────
SOURCES = {
    # 使用对程序化抓取更友好的金融教育网站（替代 Investopedia，后者有反爬限制）
    "static_pages": [
        # CFI (Corporate Finance Institute) — 服务端渲染，抓取友好
        "https://corporatefinanceinstitute.com/resources/valuation/price-earnings-ratio/",
        "https://corporatefinanceinstitute.com/resources/accounting/earnings-per-share-eps-formula/",
        "https://corporatefinanceinstitute.com/resources/valuation/fcf-formula-free-cash-flow/",
        "https://corporatefinanceinstitute.com/resources/valuation/ebitda-margin/",
        # SEC Investor.gov — 美国政府官方投资者教育网站
        "https://www.investor.gov/introduction-investing/investing-basics/investment-products",
        "https://www.investor.gov/introduction-investing/investing-basics/how-stock-markets-work",
    ],
    "wikipedia": [
        "市盈率", "净资产收益率", "自由现金流", "市净率",
        "Price–earnings ratio", "EBITDA",
    ],
    "earnings_tickers": ["BABA", "TSLA", "AAPL", "TCEHY"],
    "tavily_queries": [
        "阿里巴巴最新季度财报摘要",
        "特斯拉季报要点",
        "腾讯控股财务数据",
    ],
}

splitter = RecursiveCharacterTextSplitter(
    chunk_size=512, chunk_overlap=64,
    separators=["\n\n", "\n", "。", ".", " "],
)
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vectordb   = Chroma(
    collection_name="finance_knowledge",
    embedding_function=embeddings,
    persist_directory=settings.CHROMA_DIR,
)
tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)


def _load_static_pages() -> list[Document]:
    docs = []
    for url in SOURCES["static_pages"]:
        try:
            docs.extend(WebBaseLoader(url).load())
            logger.info(f"✓ 加载页面: {url}")
        except Exception as e:
            logger.error(f"✗ 页面加载失败 {url}: {e}")
    return docs


def _load_wikipedia() -> list[Document]:
    docs = []
    for q in SOURCES["wikipedia"]:
        try:
            lang = "zh" if any("\u4e00" <= c <= "\u9fff" for c in q) else "en"
            docs.extend(WikipediaLoader(query=q, load_max_docs=1, lang=lang).load())
        except Exception as e:
            logger.error(f"✗ Wikipedia 失败 {q}: {e}")
    return docs


def _load_earnings() -> list[Document]:
    docs = []
    for ticker in SOURCES["earnings_tickers"]:
        try:
            info = yf.Ticker(ticker).info
            text = (
                f"# {ticker} 财务摘要（来源：Yahoo Finance）\n"
                f"市盈率（P/E）: {info.get('trailingPE', 'N/A')}\n"
                f"市净率（P/B）: {info.get('priceToBook', 'N/A')}\n"
                f"EPS: {info.get('trailingEps', 'N/A')}\n"
                f"营收（TTM）: {info.get('totalRevenue', 'N/A')}\n"
                f"净利润率: {info.get('profitMargins', 'N/A')}\n"
                f"ROE: {info.get('returnOnEquity', 'N/A')}\n"
                f"行业: {info.get('industry', 'N/A')}\n"
            )
            docs.append(Document(
                page_content=text,
                metadata={"source": f"yfinance:{ticker}", "type": "earnings"},
            ))
        except Exception as e:
            logger.error(f"✗ yfinance 失败 {ticker}: {e}")
    return docs


def _load_tavily() -> list[Document]:
    docs = []
    for q in SOURCES["tavily_queries"]:
        try:
            for r in tavily.search(q, max_results=3).get("results", []):
                docs.append(Document(
                    page_content=r["content"],
                    metadata={"source": r["url"], "type": "web", "query": q},
                ))
        except Exception as e:
            logger.error(f"✗ Tavily 失败 {q}: {e}")
    return docs


def refresh_knowledge_base():
    """全量刷新知识库，由 APScheduler 调度或手动触发"""
    logger.info("═══ 知识库刷新开始 ═══")
    all_docs = (
        _load_static_pages()
        + _load_wikipedia()
        + _load_earnings()
        + _load_tavily()
    )

    if not all_docs:
        logger.error("没有获取到文档，本次刷新跳过")
        return

    chunks = splitter.split_documents(all_docs)
    logger.info(f"文档 {len(all_docs)} 篇，分块 {len(chunks)} 个")

    # 全量重建（简单可靠，避免增量更新的去重复杂度）
    vectordb.delete_collection()
    vectordb.add_documents(chunks)
    logger.info(f"═══ 知识库刷新完成，写入 {len(chunks)} chunks ═══")

    _log_refresh(len(all_docs), len(chunks))


def _log_refresh(doc_count: int, chunk_count: int):
    import aiosqlite, asyncio
    async def _write():
        async with aiosqlite.connect(settings.SQLITE_PATH) as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS kb_refresh_log "
                "(id INTEGER PRIMARY KEY, doc_count INT, chunk_count INT, refreshed_at TEXT)"
            )
            await db.execute(
                "INSERT INTO kb_refresh_log (doc_count, chunk_count, refreshed_at) "
                "VALUES (?, ?, datetime('now'))",
                (doc_count, chunk_count),
            )
            await db.commit()
    asyncio.run(_write())


def start_scheduler() -> BackgroundScheduler:
    """在 FastAPI lifespan 中调用，注册定时任务"""
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        refresh_knowledge_base, "cron",
        hour=settings.KB_REFRESH_CRON_HOUR, minute=0,
        id="kb_daily_refresh", replace_existing=True,
    )
    # 每周一额外执行，覆盖周末财报发布
    scheduler.add_job(
        refresh_knowledge_base, "cron",
        day_of_week="mon", hour=3, minute=0,
        id="kb_weekly_refresh", replace_existing=True,
    )
    scheduler.start()
    logger.info("APScheduler 已启动，知识库定时刷新已注册")
    return scheduler


# ── 命令行手动触发 ────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-now", action="store_true")
    if parser.parse_args().run_now:
        refresh_knowledge_base()
```

```python
# main.py — FastAPI lifespan 注册调度器

from contextlib import asynccontextmanager
from fastapi import FastAPI
from scripts.refresh_knowledge import start_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = start_scheduler()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
```

---

### 3.5 本地文件知识库加载（新增）

> **需求背景**：除了在线数据源（Investopedia、Wikipedia、Yahoo Finance、Tavily），金融基础知识库还需要支持从指定本地文件夹遍历所有知识文件来刷新知识库，每天随定时刷新一同更新。

#### 支持格式

| 格式 | 扩展名 | 解析库 | 说明 |
|------|--------|--------|------|
| 纯文本 | `.txt` | 内置 `pathlib` | UTF-8 读取 |
| Markdown | `.md` | 内置 `pathlib` | UTF-8 读取，保留原始格式 |
| Word 文档 | `.docx` | `python-docx` | 提取所有段落文本 |
| PDF 文档 | `.pdf` | `pymupdf`（fitz） | 逐页提取文本内容 |

#### 配置方式

```bash
# .env
KNOWLEDGE_FILES_DIR=./knowledge_files    # 知识文件目录路径，留空则跳过
KNOWLEDGE_FILES_ENABLED=true             # 是否启用本地文件知识源
```

#### 目录结构示例

```
backend/knowledge_files/
├── 金融基础/
│   ├── 股票入门.md
│   ├── 债券投资指南.pdf
│   └── 基金定投策略.docx
├── 行业分析/
│   ├── 半导体行业报告.pdf
│   └── 新能源趋势.txt
└── 内部研报/
    └── 2026Q1市场展望.docx
```

#### 实现逻辑

```python
# scripts/refresh_knowledge.py — _load_local_files() 函数

def _load_local_files() -> list[Document]:
    """递归遍历 KNOWLEDGE_FILES_DIR 下所有知识文件"""
    if not settings.KNOWLEDGE_FILES_ENABLED or not settings.KNOWLEDGE_FILES_DIR:
        return []

    knowledge_dir = Path(settings.KNOWLEDGE_FILES_DIR)
    SUPPORTED_EXTENSIONS = {".txt", ".md", ".docx", ".pdf"}

    for file_path in knowledge_dir.rglob("*"):
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        # .txt / .md → pathlib.read_text()
        # .docx      → python-docx 提取段落
        # .pdf       → pymupdf (fitz) 逐页提取文本

        docs.append(Document(
            page_content=text,
            metadata={
                "source": str(file_path),
                "type": "local_file",
                "format": ext,
                "filename": file_path.name,
            },
        ))
    return docs
```

#### 集成到刷新流程

```python
def refresh_knowledge_base():
    all_docs = (
        _load_local_files()          # ★ 新增：本地文件优先加载
        + _load_static_pages()
        + _load_wikipedia()
        + _load_earnings()
        + _load_tavily()
    )
    # ... 后续分块、入库逻辑不变
```

#### 调度

- 与现有知识库刷新共享同一调度周期（每日 `KB_REFRESH_CRON_HOUR` 时执行）
- 全量重建，确保删除的文件也会从知识库中清除
- 支持通过 `POST /admin/refresh-knowledge` 手动触发

---

### 3.6 模型质量评估框架（新增）

> **需求背景**：当模型从 Opus 替换为 ChatGPT（或其他模型）后，需要有标准化的方式判定回答质量是变好还是变差，并生成可视化对比报告。

#### 评估体系设计

##### 评估维度（5 维度加权评分）

| 维度 | 权重 | 说明 |
|------|------|------|
| accuracy（准确性） | 30% | 回答的事实、数据、概念是否准确 |
| completeness（完整性） | 25% | 是否覆盖了问题的关键知识点 |
| relevance（相关性） | 20% | 回答是否紧扣问题主题 |
| reasoning（推理质量） | 15% | 分析推理的逻辑性与深度 |
| language_quality（语言质量） | 10% | 表达的流畅性、专业性与可读性 |

##### 评估流程

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  评估数据集   │────▶│  待评估模型   │────▶│   模型回答    │
│ eval_dataset │     │ (被测模型)    │     │              │
│   .json      │     └──────────────┘     └──────┬───────┘
└──────────────┘                                  │
                                                  ▼
                     ┌──────────────┐     ┌──────────────┐
                     │  评估报告     │◀────│   裁判模型    │
                     │ (JSON/控制台) │     │ (GPT-4o)     │
                     └──────────────┘     └──────────────┘
```

##### 评估数据集结构

```json
// eval/eval_dataset.json
{
  "version": "1.0",
  "test_cases": [
    {
      "id": "finance_concept_01",
      "category": "金融概念",
      "question": "什么是市盈率？如何用它评估股票？",
      "reference_answer": "市盈率是股价与EPS的比率...",
      "expected_keywords": ["股价", "EPS", "比率", "高估"],
      "difficulty": "easy"
    }
  ]
}
```

数据集包含 8 个测试用例，覆盖 5 个类别：金融概念、行情分析、财报解读、综合分析、新闻分析、风险管理。

##### 评估报告内容

**单模型报告**（`eval/reports/report_{model}_{timestamp}.json`）：
- 综合加权评分（0-10）
- 各维度平均分
- 各题目类别得分
- 平均延迟和关键词覆盖率
- 每道题目的详细评分、优缺点评语

**模型对比报告**（`eval/reports/comparison_{modelA}_vs_{modelB}_{timestamp}.json`）：
- 总排名（按综合分排序）
- 各维度对比（哪个模型在哪个维度更强）
- 各类别对比
- 逐题胜负统计（Head-to-Head）
- 自动生成文字结论（如"Claude Opus 明显优于 GPT-4o，综合评分 8.5 vs 7.2"）

#### CLI 使用方式

```bash
# 评估单个模型
uv run python scripts/evaluate_model.py --model anthropic/claude-opus-4.6

# 评估多个模型并生成对比报告
uv run python scripts/evaluate_model.py \
    --model anthropic/claude-opus-4.6 \
    --model openai/gpt-4o \
    --compare

# 与之前保存的报告对比
uv run python scripts/evaluate_model.py \
    --model openai/gpt-4o \
    --compare-with ./eval/reports/report_anthropic_claude-opus-4.6_20260304.json
```

#### API 触发

```bash
# 通过 Admin API 触发评估
curl -X POST http://localhost:8000/admin/evaluate-models \
  -H "Authorization: Bearer your-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"models": ["anthropic/claude-opus-4.6", "openai/gpt-4o"], "compare": true}'

# 查看已有报告列表
curl http://localhost:8000/admin/eval-reports \
  -H "Authorization: Bearer your-admin-token"
```

#### 配置

```bash
# .env
EVAL_DATASET_PATH=./eval/eval_dataset.json   # 评估数据集路径
EVAL_REPORTS_DIR=./eval/reports               # 报告输出目录
EVAL_JUDGE_MODEL=openai/gpt-4o               # 裁判模型（建议用强模型）
```

#### 报告示例（控制台输出）

```
============================================================
  模型评估报告
============================================================
  模型：anthropic/claude-opus-4.6
  裁判模型：openai/gpt-4o
  评估时间：2026-03-04T15:30:00
  测试用例数：8
------------------------------------------------------------
  综合评分：8.35 / 10
  平均延迟：3.2s
  关键词覆盖率：87%
------------------------------------------------------------

  各维度平均分：
    accuracy             ████████░░ 8.5/10
    completeness         ████████░░ 8.2/10
    relevance            █████████░ 8.8/10
    reasoning            ████████░░ 7.9/10
    language_quality     █████████░ 8.6/10

  各类别表现：
    金融概念     9.0/10 (2 题)
    行情分析     7.8/10 (2 题)
    财报解读     7.5/10 (1 题)
    综合分析     8.2/10 (1 题)
    新闻分析     8.5/10 (1 题)
    风险管理     9.1/10 (1 题)
============================================================
```

---

## 4. 前端设计（轻量）

前端只负责展示，所有业务逻辑在后端完成。

### 组件清单（共 5 个文件）

| 文件 | 职责 | 行数估计 |
|------|------|----------|
| `routes/index.tsx` | Chat 主界面布局 | ~80 行 |
| `hooks/useSSEChat.ts` | SSE 流式对话 hook | ~100 行 |
| `hooks/useMarketData.ts` | TanStack Query 行情请求 | ~30 行 |
| `components/MessageRenderer.tsx` | Markdown / 数据卡片 / 步骤折叠 | ~80 行 |
| `components/PriceChart.tsx` | Recharts 折线图 | ~50 行 |

### Chat 主界面

```typescript
// src/routes/index.tsx
import { createFileRoute } from "@tanstack/react-router";
import { useSSEChat } from "../hooks/useSSEChat";
import { MessageRenderer } from "../components/MessageRenderer";

export const Route = createFileRoute("/")({
  component: ChatPage,
});

function ChatPage() {
  const { messages, isLoading, send, stop } = useSSEChat();
  const [input, setInput] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    send(input.trim());
    setInput("");
  };

  return (
    <div className="flex flex-col h-screen max-w-3xl mx-auto p-4 gap-4">
      {/* 消息列表 */}
      <div className="flex-1 overflow-auto space-y-3">
        {messages.map(m => <MessageRenderer key={m.id} message={m} />)}
        {isLoading && (
          <div className="text-slate-400 text-sm animate-pulse">Agent 分析中...</div>
        )}
      </div>

      {/* 输入区 */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="BABA 最近 7 天涨跌情况如何？"
          className="flex-1 bg-slate-800 border border-slate-600 rounded px-3 py-2 text-sm"
        />
        {isLoading
          ? <button type="button" onClick={stop} className="px-4 py-2 bg-red-700 rounded text-sm">停止</button>
          : <button type="submit" className="px-4 py-2 bg-blue-600 rounded text-sm">发送</button>
        }
      </form>
    </div>
  );
}
```

---

## 5. 项目目录结构

```
finance-qa/
│
├── frontend/                          # 轻量前端（Vite + React + bun）
│   ├── src/
│   │   ├── routes/
│   │   │   ├── __root.tsx             # 根布局 + QueryClientProvider
│   │   │   └── index.tsx              # Chat 主界面（~80行）
│   │   ├── hooks/
│   │   │   ├── useSSEChat.ts          # SSE 流式对话（~100行）
│   │   │   └── useMarketData.ts       # TanStack Query 行情请求
│   │   └── components/
│   │       ├── MessageRenderer.tsx    # Markdown + 数据卡片 + 步骤折叠
│   │       └── PriceChart.tsx         # Recharts 折线图
│   ├── bun.lockb                      # bun 锁文件
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts                 # 配置 proxy → 后端 :8000
│
├── backend/                           # 后端（重点）
│   ├── pyproject.toml                 # uv 项目配置
│   ├── uv.lock                        # 锁文件（提交到 git）
│   ├── main.py                        # FastAPI + lifespan（调度器）
│   │
│   ├── skills/                        # ★ LangGraph Skills
│   │   ├── __init__.py                # ALL_TOOLS 统一导出
│   │   ├── market_data/
│   │   │   ├── tool.py
│   │   │   ├── prompt.txt
│   │   │   └── test_cases.json
│   │   ├── news/
│   │   │   ├── tool.py
│   │   │   ├── prompt.txt
│   │   │   └── test_cases.json
│   │   ├── rag_search/
│   │   │   ├── tool.py
│   │   │   ├── prompt.txt
│   │   │   └── test_cases.json
│   │   ├── web_search/
│   │   │   ├── tool.py
│   │   │   └── test_cases.json
│   │   └── technical_metrics/
│   │       ├── tool.py
│   │       └── test_cases.json
│   │
│   ├── core/agent/
│   │   ├── graph.py                   # create_react_agent（prebuilt）
│   │   └── state.py                   # AgentState
│   │
│   ├── services/
│   │   ├── llm_client.py              # OpenRouter 封装
│   │   └── cache_service.py           # Redis + @cached 装饰器
│   │
│   ├── scripts/
│   │   ├── refresh_knowledge.py       # ★ 定时刷新 + APScheduler + 本地文件加载
│   │   └── evaluate_model.py          # ★ 模型质量评估 + 对比报告
│   │
│   ├── eval/                           # 模型评估相关
│   │   ├── eval_dataset.json           # 标准评估数据集（8 测试用例）
│   │   └── reports/                    # 评估报告输出目录
│   │
│   ├── knowledge_files/                # 本地知识文件目录（可配置路径）
│   │   └── (txt/md/docx/pdf files)
│   │
│   ├── prompts/
│   │   ├── react_agent.txt            # ReAct System Prompt
│   │   └── loader.py                  # 合并 Skill prompt.txt
│   │
│   ├── api/routes/
│   │   ├── query.py                   # POST /api/query (SSE)
│   │   ├── market.py                  # GET /api/market/{ticker}
│   │   └── admin.py                   # POST /admin/refresh-knowledge
│   │
│   ├── config/
│   │   ├── settings.py                # pydantic-settings
│   │   └── models.py                  # MODEL_ROUTING
│   │
│   └── tests/
│       ├── test_skills.py             # 各 Skill 单元测试
│       └── test_agent.py              # Agent 集成测试
│
├── docker-compose.yml                 # Redis + ChromaDB
├── .env.example
└── README.md
```

---

## 6. 分阶段开发计划

### Phase 1 · 后端骨架 + OpenRouter · Day 1

| 任务 | 关键库 / 命令 | 工时 |
|------|--------------|------|
| `uv init`，pyproject.toml，`uv add` 核心依赖 | `uv` | 0.5h |
| pydantic-settings 配置，MODEL_ROUTING | `pydantic-settings` | 0.5h |
| OpenRouter LLM Client（`get_langchain_model`） | `openai` SDK | 1h |
| MarketData Skill（yfinance + `@cached`） | `yfinance`, `redis` | 1.5h |
| News Skill（NewsAPI + LLM 摘要） | `newsapi-python` | 1h |
| LangGraph Agent（`create_react_agent` prebuilt） | `langgraph` | 1h |
| SSE 流式接口 `/api/query` | `fastapi` | 1h |
| Docker Compose：Redis | — | 0.5h |

**验收**：`uv run uvicorn main:app` 启动，curl 能回答「BABA 7天涨跌」，流式输出

---

### Phase 2 · RAG Skill + 知识库 · Day 2

| 任务 | 关键库 | 工时 |
|------|--------|------|
| ChromaDB 初始化，Embedding 配置 | `langchain-chroma`, `langchain-openai` | 0.5h |
| RAG Skill：BM25 + 向量 Hybrid 检索 | `rank-bm25`, `langchain-chroma` | 1.5h |
| BGE Reranker ONNX 接入 | `onnxruntime` + `optimum` | 0.5h |
| WebSearch Skill（Tavily） | `tavily-python` | 0.5h |
| TechnicalMetrics Skill（pandas-ta） | `pandas-ta` | 0.5h |
| RAG 防幻觉 Prompt 调试 | — | 1h |
| Skill test_cases.json + `uv run pytest` | `pytest-asyncio` | 0.5h |

**验收**：`uv run pytest tests/test_skills.py` 全通过

---

### Phase 3 · 知识库定时刷新脚本 · Day 3 上午

| 任务 | 关键库 | 工时 |
|------|--------|------|
| refresh_knowledge.py 四类来源加载函数 | `langchain-community`, `WikipediaLoader` | 1.5h |
| APScheduler 注册，FastAPI lifespan 集成 | `apscheduler` | 0.5h |
| SQLite 刷新日志（aiosqlite） | `aiosqlite` | 0.5h |
| `/admin/refresh-knowledge` 手动触发接口 | `fastapi` | 0.5h |
| 首次全量刷新，验证 ChromaDB chunk 数量 | — | 0.5h |

**验收**：`uv run python scripts/refresh_knowledge.py --run-now` 成功，日志写入 SQLite

---

### Phase 4 · 前端 + 联调 · Day 3 下午 + Day 4 上午

| 任务 | 关键库 | 工时 |
|------|--------|------|
| `bun create vite . --template react-ts`，TanStack Router/Query 安装 | `bun` | 0.5h |
| Tailwind v4 配置（Vite 插件，零配置） | `@tailwindcss/vite` | 0.3h |
| TanStack Router 路由，根布局 | `@tanstack/react-router` | 0.5h |
| `useSSEChat` hook（原生 EventSource / fetch） | — | 1h |
| `useMarketData` hook（TanStack Query） | `@tanstack/react-query` | 0.5h |
| `MessageRenderer`：Markdown + 数据卡片 + 步骤折叠 | `react-markdown` | 1h |
| `PriceChart`：Recharts LineChart | `recharts` | 0.5h |
| vite.config.ts proxy 配置（`/api → :8000`） | — | 0.2h |
| 端到端联调（行情 / RAG / 复合三类问题）| — | 1.5h |

**验收**：`bun dev` 启动，三类问题前端正常渲染，走势图显示

---

### Phase 5 · 打磨 + 交付 · Day 4 下午 + Day 5

| 任务 | 工时 |
|------|------|
| 错误处理：API 失败 / Redis 降级 / LLM 超时 | 1h |
| `uv run ruff check . && uv run mypy .` 代码规范扫描 | 0.5h |
| Docker Compose 完整版（前端构建 + 后端 + Redis） | 0.5h |
| README：架构图 + 启动说明 + Prompt 设计说明 + 数据来源 | 1h |
| `.env.example` 完善 | 0.2h |
| 演示脚本 + 3 分钟录屏 | 1h |

---

### Phase 6 · 额外需求 · Day 6（新增）

#### 6a. 本地文件知识库加载

| 任务 | 关键库 | 工时 |
|------|--------|------|
| `python-docx` + `pymupdf` 依赖安装 | `uv add python-docx pymupdf` | 0.2h |
| `KNOWLEDGE_FILES_DIR` 配置项 | `pydantic-settings` | 0.2h |
| `_load_local_files()` 实现：遍历 txt/md/docx/pdf | `python-docx`, `pymupdf` | 1.5h |
| 集成到 `refresh_knowledge_base()` 刷新流程 | — | 0.3h |
| 准备示例知识文件，测试各格式解析 | — | 0.5h |
| 更新 `.env.example` 和文档 | — | 0.3h |

**验收**：放入 txt/md/docx/pdf 文件到 `knowledge_files/` 目录，运行 `uv run python scripts/refresh_knowledge.py --run-now`，确认各格式文件被正确解析并写入 ChromaDB

#### 6b. 模型质量评估框架

| 任务 | 关键库 | 工时 |
|------|--------|------|
| 设计 5 维度评分体系 + 裁判 Prompt | — | 0.5h |
| 编写评估数据集 `eval_dataset.json`（8 题，覆盖 5 类） | — | 1h |
| `evaluate_model.py` 核心逻辑：单模型评估 | `openai` SDK | 1.5h |
| 对比报告生成：排名 / 维度对比 / 逐题 Head-to-Head / 结论 | — | 1h |
| Admin API：`/admin/evaluate-models` + `/admin/eval-reports` | `fastapi` | 0.5h |
| 端到端测试：2 个模型对比评估，验证报告输出 | — | 0.5h |

**验收**：
```bash
uv run python scripts/evaluate_model.py \
    --model anthropic/claude-opus-4.6 \
    --model openai/gpt-4o \
    --compare
```
生成 3 个文件：2 份单模型报告 + 1 份对比报告，对比报告包含明确的质量判定结论

---

## 7. 三方库选型清单

### 后端

| 功能 | 库 | 说明 |
|------|----|------|
| 包管理 | **`uv`** | 极速，锁文件，替代 poetry/pip |
| LLM 调用 | `openai`（base_url=OpenRouter） | 一套 SDK，多模型 |
| Agent 框架 | `langgraph` + `langgraph.prebuilt` | ReAct 开箱即用 |
| 行情数据 | `yfinance` | 免费，全球市场 |
| 新闻数据 | `newsapi-python` | 官方 SDK |
| Web 搜索 | `tavily-python` | LLM 友好结果 |
| 技术指标 | `pandas-ta` | 100+ 指标 |
| 向量数据库 | `langchain-chroma` | 本地运行 |
| Hybrid 检索 | `rank-bm25` + ChromaDB | 双路召回 |
| Reranker | `onnxruntime` + `optimum` | BGE-reranker-v2-m3 ONNX 本地推理，免费无 API key |
| 文档加载 | `langchain-community` | WebLoader / Wikipedia / PDF |
| 文本分块 | `langchain-text-splitters` | RecursiveCharacterTextSplitter |
| 定时任务 | `apscheduler` | 轻量，无需 Celery |
| 缓存 | `redis` | 官方 SDK |
| 后端框架 | `fastapi` + `uvicorn` | SSE 原生支持 |
| 配置管理 | `pydantic-settings` | .env 类型安全 |
| 刷新日志 | `aiosqlite` | SQLite 异步，轻量够用 |
| Word 文档解析 | `python-docx` | 提取 .docx 段落文本（新增） |
| PDF 文档解析 | `pymupdf` | 提取 .pdf 逐页文本（新增） |
| 代码规范 | `ruff` + `mypy` | 快速 lint + 类型检查 |
| 测试 | `pytest` + `pytest-asyncio` | 标准测试框架 |

### 前端

| 功能 | 库 | 说明 |
|------|----|------|
| 包管理 | **`bun`** | 快 10-25x，替代 npm |
| 构建工具 | `vite` | 冷启动 < 300ms，替代 Next.js |
| 路由 | `@tanstack/react-router` | 类型安全，文件路由 |
| 数据请求 | `@tanstack/react-query` | 缓存 / 状态 / 重试一体化 |
| 流式输出 | 原生 `fetch` + `ReadableStream` | 无需额外依赖 |
| 样式 | `tailwindcss` v4 | Vite 插件版，零配置 |
| Markdown | `react-markdown` + `remark-gfm` | 轻量渲染 |
| 图标 | `lucide-react` | 按需引入 |
| 图表 | `recharts` | React 声明式图表 |

---

## 8. 环境配置与启动

### .env 配置

```bash
# ── LLM（OpenRouter）─────────────────────────────────────
OPENROUTER_API_KEY=sk-or-v1-...
DEFAULT_MODEL=anthropic/claude-3.5-sonnet
ROUTER_MODEL=openai/gpt-4o-mini
RAG_MODEL=openai/gpt-4o-mini
APP_URL=http://localhost:5173             # Vite 默认端口

# ── 数据 API ──────────────────────────────────────────────
NEWSAPI_KEY=...
TAVILY_API_KEY=...
# Reranker（BGE ONNX 本地推理，无需 API key）
RERANKER_MODEL_DIR=./models/bge-reranker-v2-m3-onnx

# ── 基础设施 ──────────────────────────────────────────────
REDIS_HOST=localhost
REDIS_PORT=6379
CHROMA_DIR=./chroma_db
SQLITE_PATH=./logs.db

# ── 定时刷新 ──────────────────────────────────────────────
KB_REFRESH_CRON_HOUR=2
KB_REFRESH_ENABLED=true

# ── 本地知识文件目录 ──────────────────────────────────────
KNOWLEDGE_FILES_DIR=./knowledge_files
KNOWLEDGE_FILES_ENABLED=true

# ── 模型质量评估 ──────────────────────────────────────────
EVAL_DATASET_PATH=./eval/eval_dataset.json
EVAL_REPORTS_DIR=./eval/reports
EVAL_JUDGE_MODEL=openai/gpt-4o

# ── 缓存 TTL（秒）────────────────────────────────────────
CACHE_TTL_MARKET=3600
CACHE_TTL_NEWS=1800
CACHE_TTL_EMBEDDING=86400
CACHE_TTL_WEB_SEARCH=900

# ── 安全 ─────────────────────────────────────────────────
ADMIN_TOKEN=your-admin-token
```

### 本地开发启动

```bash
# ── 基础设施 ──────────────────────────────────────────────
docker-compose up -d           # Redis

# ── 后端 ──────────────────────────────────────────────────
cd backend
uv sync                        # 根据 uv.lock 安装依赖
uv run python scripts/refresh_knowledge.py --run-now   # 首次入库
uv run uvicorn main:app --reload --port 8000

# ── 前端 ──────────────────────────────────────────────────
cd frontend
bun install
bun dev                        # → http://localhost:5173

# ── 测试 ──────────────────────────────────────────────────
cd backend
uv run pytest                  # 单元 + 集成测试
uv run ruff check .            # lint
```

### docker-compose.yml

```yaml
services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes: ["redis_data:/data"]
    command: redis-server --save 60 1

  backend:
    build: ./backend
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [redis]
    volumes:
      - ./backend/chroma_db:/app/chroma_db
      - ./backend/logs.db:/app/logs.db

  frontend:
    build: ./frontend
    ports: ["5173:5173"]
    depends_on: [backend]

volumes:
  redis_data:
```

### Dockerfile（后端）

```dockerfile
FROM python:3.12-slim
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev    # 仅安装生产依赖，不安装 dev
COPY . .
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

*文档版本：v2.3 · 2026-03*  
*v2.3 变更：新增本地文件知识库加载（3.5）、模型质量评估框架（3.6）、Phase 6 开发计划*
