"""Model routing: default model (agent) and coordinator model."""

from config.settings import settings

MODEL_ROUTING: dict[str, str] = {
    "market_analyst": settings.DEFAULT_MODEL,
    "coordinator": settings.COORDINATOR_MODEL,
}

if settings.OVERRIDE_ALL_MODELS:
    for key in MODEL_ROUTING:
        MODEL_ROUTING[key] = settings.OVERRIDE_ALL_MODELS
