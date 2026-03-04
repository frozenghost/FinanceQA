.PHONY: help install dev build start stop restart logs clean test

# 默认目标
help:
	@echo "金融资产问答系统 - 可用命令:"
	@echo ""
	@echo "  make install      - 安装所有依赖"
	@echo "  make dev          - 启动开发环境"
	@echo "  make build        - 构建 Docker 镜像"
	@echo "  make start        - 启动所有服务"
	@echo "  make stop         - 停止所有服务"
	@echo "  make restart      - 重启所有服务"
	@echo "  make logs         - 查看服务日志"
	@echo "  make clean        - 清理数据和缓存"
	@echo "  make test         - 运行测试"
	@echo "  make kb-refresh   - 刷新知识库"
	@echo "  make kb-test      - 测试知识库数据源"
	@echo ""

# 安装依赖
install:
	@echo "安装后端依赖..."
	cd backend && uv sync
	@echo "安装前端依赖..."
	cd frontend && bun install
	@echo "✅ 依赖安装完成"

# 开发环境
dev:
	@echo "启动开发环境..."
	@echo "后端: http://localhost:8000"
	@echo "前端: http://localhost:5173"
	@echo ""
	@echo "在两个终端分别运行:"
	@echo "  终端1: cd backend && uv run uvicorn main:app --reload"
	@echo "  终端2: cd frontend && bun run dev"

# 构建 Docker 镜像
build:
	@echo "构建 Docker 镜像..."
	docker-compose build

# 启动服务
start:
	@echo "启动所有服务..."
	docker-compose up -d
	@echo "✅ 服务已启动"
	@echo "前端: http://localhost:5173"
	@echo "后端: http://localhost:8000"
	@echo "API 文档: http://localhost:8000/docs"

# 停止服务
stop:
	@echo "停止所有服务..."
	docker-compose stop
	@echo "✅ 服务已停止"

# 重启服务
restart:
	@echo "重启所有服务..."
	docker-compose restart
	@echo "✅ 服务已重启"

# 查看日志
logs:
	docker-compose logs -f

# 清理
clean:
	@echo "清理数据和缓存..."
	docker-compose down -v
	rm -rf backend/chroma_db/*
	rm -f backend/data/app.db
	docker-compose exec redis redis-cli FLUSHALL || true
	@echo "✅ 清理完成"

# 测试
test:
	@echo "运行后端测试..."
	cd backend && uv run pytest
	@echo "运行前端测试..."
	cd frontend && bun test

# 刷新知识库
kb-refresh:
	@echo "刷新知识库..."
	cd backend && uv run python scripts/refresh_knowledge.py --run-now
	@echo "✅ 知识库刷新完成"

# 测试知识库数据源
kb-test:
	@echo "测试知识库数据源..."
	cd backend && uv run python scripts/test_fetchers.py

# 查看知识库日志
kb-logs:
	@echo "最近的知识库刷新记录:"
	sqlite3 backend/data/app.db "SELECT * FROM kb_refresh_log ORDER BY id DESC LIMIT 10;"

# 下载重排序模型
download-reranker:
	@echo "下载 BGE 重排序模型..."
	cd backend && uv run --with optimum --with torch python scripts/download_reranker.py
	@echo "✅ 模型下载完成"

# 运行模型评估
evaluate:
	@echo "运行模型评估..."
	cd backend && uv run python scripts/evaluate_model.py

# 格式化代码
format:
	@echo "格式化后端代码..."
	cd backend && uv run ruff format .
	@echo "✅ 代码格式化完成"

# 代码检查
lint:
	@echo "检查后端代码..."
	cd backend && uv run ruff check .
	@echo "检查前端代码..."
	cd frontend && bun run lint

# 查看服务状态
status:
	@echo "服务状态:"
	docker-compose ps

# 进入 Redis CLI
redis-cli:
	docker-compose exec redis redis-cli

# 查看 Redis 缓存
redis-keys:
	docker-compose exec redis redis-cli KEYS '*'

# 清空 Redis 缓存
redis-flush:
	docker-compose exec redis redis-cli FLUSHALL
	@echo "✅ Redis 缓存已清空"
