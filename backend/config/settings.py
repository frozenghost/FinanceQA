"""Application settings powered by pydantic-settings. Reads from .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM (OpenRouter) ─────────────────────────────────────
    OPENROUTER_API_KEY: str = ""
    DEFAULT_MODEL: str = "anthropic/claude-3.5-sonnet"
    ROUTER_MODEL: str = "openai/gpt-4o-mini"
    RAG_MODEL: str = "openai/gpt-4o-mini"
    APP_URL: str = "http://localhost:5173"

    # ── 数据 API ──────────────────────────────────────────────
    NEWSAPI_KEY: str = ""
    TAVILY_API_KEY: str = ""

    # ── Reranker（BGE-reranker-v2-m3 ONNX 本地推理）────────
    RERANKER_MODEL_DIR: str = "./models/bge-reranker-v2-m3-onnx"

    # ── Embedding 配置（支持 OpenAI / OpenRouter / 任何兼容接口）──
    EMBEDDING_API_KEY: str = ""          # 留空则回退到 OPENROUTER_API_KEY
    EMBEDDING_BASE_URL: str = ""         # 留空则用 OpenAI 默认；设为 OpenRouter 等地址即可切换
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # ── 兼容旧配置 ───────────────────────────────────────────
    OPENAI_API_KEY: str = ""             # 如果设了这个，EMBEDDING_API_KEY 留空时也会用它

    # ── 基础设施 ──────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    CHROMA_DIR: str = "./chroma_db"
    SQLITE_PATH: str = "./logs.db"

    # ── 定时刷新 ──────────────────────────────────────────────
    KB_REFRESH_CRON_HOUR: int = 2
    KB_REFRESH_ENABLED: bool = True

    # ── 本地知识文件目录（支持 txt, md, docx, pdf）──────────
    KNOWLEDGE_FILES_DIR: str = ""         # 留空则跳过本地文件加载
    KNOWLEDGE_FILES_ENABLED: bool = True  # 是否启用本地文件知识源

    # ── 模型质量评估 ────────────────────────────────────────
    EVAL_DATASET_PATH: str = "./eval/eval_dataset.json"
    EVAL_REPORTS_DIR: str = "./eval/reports"
    EVAL_JUDGE_MODEL: str = "openai/gpt-4o"  # 用于评分的裁判模型

    # ── 缓存 TTL（秒）────────────────────────────────────────
    CACHE_TTL_MARKET: int = 3600
    CACHE_TTL_NEWS: int = 1800
    CACHE_TTL_EMBEDDING: int = 86400
    CACHE_TTL_WEB_SEARCH: int = 900
    CACHE_TTL_TECHNICAL: int = 3600

    # ── 安全 ─────────────────────────────────────────────────
    ADMIN_TOKEN: str = "your-admin-token"

    # ── 模型覆盖（可选，一行切换所有模型）───────────────────
    OVERRIDE_ALL_MODELS: str = ""


settings = Settings()
