"""Model routing configuration for OpenRouter multi-model support."""

from config.settings import settings

MODEL_ROUTING: dict[str, str] = {
    "router": settings.ROUTER_MODEL,            # 分类任务，低延迟
    "market_analyst": settings.DEFAULT_MODEL,    # 分析任务，推理强
    "rag_qa": settings.RAG_MODEL,                # 有 context，中模型够
    "coordinator": settings.ROUTER_MODEL,        # 协调器，规划工具调用（使用快速模型）
}

# 支持环境变量全局覆盖，演示时一行切换
if settings.OVERRIDE_ALL_MODELS:
    for key in MODEL_ROUTING:
        MODEL_ROUTING[key] = settings.OVERRIDE_ALL_MODELS
