"""FastAPI application entry point with lifespan for scheduler management."""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.admin import router as admin_router
from api.routes.market import router as market_router
from api.routes.query import router as query_router
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage APScheduler lifecycle."""
    scheduler = None

    if settings.KB_REFRESH_ENABLED:
        try:
            from scripts.refresh_knowledge import start_scheduler

            scheduler = start_scheduler()
            logger.info("APScheduler started — knowledge base refresh registered")
        except Exception as e:
            logger.warning(f"APScheduler failed to start (main service unaffected): {e}")

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler shut down")


app = FastAPI(
    title="Finance QA System",
    description="Finance QA — LangGraph ReAct Agent + OpenRouter",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", settings.APP_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query_router, tags=["Query"])
app.include_router(market_router, tags=["Market"])
app.include_router(admin_router, tags=["Admin"])


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "name": "Finance QA System",
        "version": "0.1.0",
        "docs": "/docs",
    }
