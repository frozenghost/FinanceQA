"""Application settings powered by pydantic-settings. Reads from .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration loaded from environment and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM (OpenRouter) ─────────────────────────────────────
    OPENROUTER_API_KEY: str = ""
    DEFAULT_MODEL: str = "anthropic/claude-3.5-sonnet"      # main agent, analysis
    COORDINATOR_MODEL: str = "openai/gpt-4o-mini"          # coordinator, tool planning
    APP_URL: str = "http://localhost:5173"

    # ── Data API ──────────────────────────────────────────────
    SERPAPI_KEY: str = ""
    TAVILY_API_KEY: str = ""

    # ── Reranker (BGE-reranker-v2-m3 ONNX Local Inference) ─────────
    RERANKER_MODEL_DIR: str = "./models/bge-reranker-v2-m3-onnx"

    # ── Embedding Config (Supports OpenAI / OpenRouter / Any Compatible Interface) ───
    EMBEDDING_API_KEY: str = ""          # Leave empty to fallback to OPENROUTER_API_KEY
    EMBEDDING_BASE_URL: str = ""         # Leave empty for OpenAI default; set to OpenRouter or other address to switch
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # ── Legacy Config Compatibility ───────────────────────────────────────────
    OPENAI_API_KEY: str = ""             # If set, EMBEDDING_API_KEY will also use this when empty

    # ── Infrastructure ──────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    USE_REDIS_CHECKPOINTER: bool = False
    CHECKPOINT_REDIS_PREFIX: str = ""
    CHROMA_DIR: str = "./chroma_db"
    SQLITE_PATH: str = "./logs.db"

    # ── Scheduled Refresh ──────────────────────────────────────────────
    KB_REFRESH_CRON_HOUR: int = 2
    KB_REFRESH_ENABLED: bool = True

    # ── Local Knowledge Files Directory (supports txt, md, docx, pdf) ───────────
    KNOWLEDGE_FILES_DIR: str = ""         # Leave empty to skip local file loading
    KNOWLEDGE_FILES_ENABLED: bool = True  # Whether to enable local file knowledge source

    # ── Model Quality Evaluation ────────────────────────────────────────
    EVAL_DATASET_PATH: str = "./eval/eval_dataset.json"
    EVAL_REPORTS_DIR: str = "./eval/reports"
    EVAL_JUDGE_MODEL: str = "openai/gpt-4o"  # Judge model for scoring

    # ── Cache TTL (seconds) ─────────────────────────────────────────
    CACHE_TTL_MARKET: int = 3600
    CACHE_TTL_NEWS: int = 1800
    CACHE_TTL_EMBEDDING: int = 86400
    CACHE_TTL_WEB_SEARCH: int = 900
    CACHE_TTL_TECHNICAL: int = 3600

    # ── Security ─────────────────────────────────────────────────
    ADMIN_TOKEN: str = "your-admin-token"

    # ── Model Override (Optional, one line to switch all models) ───────────────────
    OVERRIDE_ALL_MODELS: str = ""

    # ── Agent Mode Config ────────────────────────────────────────
    USE_COORDINATOR: bool = True  # Whether to use coordinator mode (force tool usage, reduce hallucinations)


settings = Settings()
