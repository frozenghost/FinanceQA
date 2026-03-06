"""Model routing configuration for OpenRouter multi-model support."""

from config.settings import settings

MODEL_ROUTING: dict[str, str] = {
    "router": settings.ROUTER_MODEL,            # routing, low latency
    "market_analyst": settings.DEFAULT_MODEL,   # analysis, stronger reasoning
    "rag_qa": settings.RAG_MODEL,              # RAG with context
    "coordinator": settings.ROUTER_MODEL,       # coordinator, tool planning (fast model)
}

# Overridable via env; single-line switch for demos
if settings.OVERRIDE_ALL_MODELS:
    for key in MODEL_ROUTING:
        MODEL_ROUTING[key] = settings.OVERRIDE_ALL_MODELS
