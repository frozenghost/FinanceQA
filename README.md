# 金融资产问答系统

基于 LangGraph + RAG 的智能金融问答系统，支持市场数据查询、技术指标分析、新闻搜索和知识库检索。

## 🚀 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+ (推荐使用 Bun)
- Docker & Docker Compose
- Redis

### 1. 克隆项目

```bash
git clone <repository-url>
cd finance-qa-system
```

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入必要的 API 密钥
# - OPENAI_API_KEY 或 OPENROUTER_API_KEY
# - TAVILY_API_KEY (可选，用于网络搜索)
# - NEWS_API_KEY (可选，用于新闻查询)
```

### 3. 启动服务

#### 方式一：使用 Docker Compose (推荐)

```bash
# 构建并启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

服务地址：
- 前端: http://localhost:5173
- 后端 API: http://localhost:8000
- API 文档: http://localhost:8000/docs

#### 方式二：本地开发

**后端:**

```bash
cd backend

# 安装 uv (如果未安装)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 创建虚拟环境并安装依赖
uv sync

# 启动后端服务
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**前端:**

```bash
cd frontend

# 安装 bun (如果未安装)
curl -fsSL https://bun.sh/install | bash

# 安装依赖
bun install

# 启动开发服务器
bun run dev
```

## 📚 核心功能

### 1. 智能问答 Agent

基于 LangGraph 的 ReAct Agent，支持多轮对话和工具调用：

- 🔍 **RAG 知识库检索**: 混合检索 (向量 + BM25) + BGE 重排序
- 📊 **市场数据查询**: 实时股价、历史数据、技术指标
- 📈 **技术指标分析**: MA, RSI, MACD, Bollinger Bands 等
- 📰 **新闻搜索**: 金融新闻和公司动态
- 🌐 **网络搜索**: Tavily 实时搜索

### 2. 可配置知识库

支持多种数据源的知识库构建：

- 📄 **本地文件**: txt, md, docx, pdf
- 🌐 **网页抓取**: 静态网页内容
- 📖 **维基百科**: 中英文自动识别
- 💰 **财务数据**: Yahoo Finance 公司数据
- 🔎 **网络搜索**: Tavily 搜索结果

配置文件: `backend/config/knowledge_sources.json`

### 3. 定时任务

- 每日自动刷新知识库
- 每周一额外刷新（覆盖周末财报）
- 可配置刷新时间

## 🛠️ 常用命令

### 快捷脚本

项目提供了跨平台的命令脚本，简化常用操作：

**Linux/macOS (使用 Makefile):**
```bash
make help          # 查看所有可用命令
make start         # 启动所有服务
make stop          # 停止所有服务
make kb-refresh    # 刷新知识库
make logs          # 查看日志
```

**Windows (使用 PowerShell):**
```powershell
.\commands.ps1 help          # 查看所有可用命令
.\commands.ps1 start         # 启动所有服务
.\commands.ps1 stop          # 停止所有服务
.\commands.ps1 kb-refresh    # 刷新知识库
.\commands.ps1 logs          # 查看日志
```

**Windows (使用 CMD):**
```cmd
commands.bat help          # 查看所有可用命令
commands.bat start         # 启动所有服务
commands.bat stop          # 停止所有服务
commands.bat kb-refresh    # 刷新知识库
```

### 后端命令

```bash
cd backend

# 开发服务器
uv run uvicorn main:app --reload

# 运行测试
uv run pytest

# 代码格式化
uv run ruff format .

# 代码检查
uv run ruff check .

# 类型检查
uv run mypy .

# 手动刷新知识库
uv run python scripts/refresh_knowledge.py --run-now

# 测试数据源
uv run python scripts/test_fetchers.py

# 测试特定 fetcher
uv run python scripts/test_fetchers.py WikipediaFetcher

# 下载重排序模型
uv run --with optimum --with torch python scripts/download_reranker.py

# 运行模型评估
uv run python scripts/evaluate_model.py
```

### 前端命令

```bash
cd frontend

# 开发服务器
bun run dev

# 构建生产版本
bun run build

# 预览生产构建
bun run preview

# 类型检查
bun run lint

# 运行测试
bun test
```

### Docker 命令

```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f [service_name]

# 重启服务
docker-compose restart [service_name]

# 停止服务
docker-compose stop

# 停止并删除容器
docker-compose down

# 重新构建并启动
docker-compose up -d --build

# 清理所有数据（包括 volumes）
docker-compose down -v
```

### 数据库命令

```bash
# 查看知识库刷新日志
sqlite3 backend/data/app.db "SELECT * FROM kb_refresh_log ORDER BY id DESC LIMIT 10;"

# 查看 Redis 缓存
docker-compose exec redis redis-cli
> KEYS *
> GET market_data:AAPL:1d
> FLUSHALL  # 清空所有缓存
```

## 📁 项目结构

```
.
├── backend/                    # Python 后端
│   ├── api/                   # FastAPI 路由
│   ├── config/                # 配置文件
│   │   ├── knowledge_sources.json  # 知识库数据源配置
│   │   ├── models.py          # Pydantic 模型
│   │   └── settings.py        # 环境配置
│   ├── core/                  # 核心逻辑
│   │   └── agent/            # LangGraph Agent
│   ├── services/              # 服务层
│   │   ├── fetchers/         # 数据获取器
│   │   ├── cache_service.py  # Redis 缓存
│   │   ├── embedding.py      # 向量嵌入
│   │   ├── llm_client.py     # LLM 客户端
│   │   └── knowledge_manager.py  # 知识库管理
│   ├── skills/                # Agent 技能
│   │   ├── market_data/      # 市场数据
│   │   ├── news/             # 新闻搜索
│   │   ├── rag_search/       # RAG 检索
│   │   ├── technical_metrics/ # 技术指标
│   │   └── web_search/       # 网络搜索
│   ├── scripts/               # 工具脚本
│   │   ├── refresh_knowledge.py   # 刷新知识库
│   │   ├── test_fetchers.py       # 测试数据源
│   │   ├── download_reranker.py   # 下载模型
│   │   └── evaluate_model.py      # 模型评估
│   ├── docs/                  # 文档
│   ├── tests/                 # 测试
│   ├── main.py               # FastAPI 入口
│   └── pyproject.toml        # Python 依赖
│
├── frontend/                  # React 前端
│   ├── src/
│   │   ├── components/       # React 组件
│   │   ├── hooks/            # 自定义 Hooks
│   │   ├── routes/           # 路由页面
│   │   └── main.tsx          # 入口文件
│   ├── package.json          # Node 依赖
│   └── vite.config.ts        # Vite 配置
│
├── docker-compose.yml         # Docker 编排
├── .env.example              # 环境变量模板
└── README.md                 # 本文件
```

## 🔧 配置知识库

### 查看当前配置

```bash
cat backend/config/knowledge_sources.json
```

### 添加新的数据源

编辑 `backend/config/knowledge_sources.json`:

```json
{
  "sources": [
    {
      "name": "my_custom_source",
      "type": "web",
      "enabled": true,
      "fetcher": "WebPageFetcher",
      "config": {
        "urls": ["https://example.com/page"]
      }
    }
  ]
}
```

### 测试配置

```bash
cd backend
uv run python scripts/test_fetchers.py
```

### 应用更改

```bash
cd backend
uv run python scripts/refresh_knowledge.py --run-now
```

## 🚀 性能优化

知识库刷新采用异步并发架构，所有数据源同时获取，大幅提升刷新速度。

## 📖 文档

- [开发计划](development-plan-v2.2.md)

## 🧪 测试

### 后端测试

```bash
cd backend

# 运行所有测试
uv run pytest

# 运行特定测试文件
uv run pytest tests/test_agent.py

# 运行带覆盖率的测试
uv run pytest --cov=. --cov-report=html

# 测试 Agent
uv run pytest tests/test_agent.py -v

# 测试 Skills
uv run pytest tests/test_skills.py -v
```

### 前端测试

```bash
cd frontend

# 运行测试
bun test

# 监听模式
bun test --watch
```

## 🔍 故障排查

### 后端无法启动

1. 检查 Python 版本: `python --version` (需要 3.12+)
2. 检查环境变量: `cat .env`
3. 检查 Redis 连接: `docker-compose ps redis`
4. 查看详细日志: `docker-compose logs backend`

### 知识库为空

1. 检查数据源配置: `cat backend/config/knowledge_sources.json`
2. 测试数据源: `cd backend && uv run python scripts/test_fetchers.py`
3. 手动刷新: `cd backend && uv run python scripts/refresh_knowledge.py --run-now`
4. 查看刷新日志

### 前端无法连接后端

1. 确认后端正在运行: `curl http://localhost:8000/health`
2. 检查 CORS 配置
3. 查看浏览器控制台错误

### Redis 连接失败

```bash
# 检查 Redis 状态
docker-compose ps redis

# 重启 Redis
docker-compose restart redis

# 查看 Redis 日志
docker-compose logs redis
```

## 🚀 部署

### 生产环境部署

1. 设置生产环境变量
2. 构建 Docker 镜像
3. 使用 docker-compose 启动

```bash
# 生产环境启动
docker-compose -f docker-compose.yml up -d

# 查看日志
docker-compose logs -f
```

### 环境变量配置

生产环境必需的环境变量：

```bash
# LLM API
OPENAI_API_KEY=sk-xxx
# 或
OPENROUTER_API_KEY=sk-or-xxx

# 可选 API
TAVILY_API_KEY=tvly-xxx
NEWS_API_KEY=xxx

# 数据库
REDIS_URL=redis://redis:6379/0

# 知识库
KNOWLEDGE_FILES_ENABLED=true
KNOWLEDGE_FILES_DIR=/app/knowledge_files
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 🔗 相关链接

- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [TanStack Router](https://tanstack.com/router)
- [uv 文档](https://docs.astral.sh/uv/)
- [Bun 文档](https://bun.sh/docs)
