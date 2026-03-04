"""Knowledge base refresh script with APScheduler integration.

Usage:
    uv run python scripts/refresh_knowledge.py --run-now
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure the backend root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from services.knowledge_manager import KnowledgeManager

logger = logging.getLogger(__name__)


def refresh_knowledge_base():
    """Full refresh of the knowledge base. Called by APScheduler or manually."""
    try:
        manager = KnowledgeManager()
        stats = manager.refresh_knowledge_base()
        _log_refresh(stats["documents"], stats["chunks"])
    except Exception as e:
        logger.error(f"Knowledge base refresh failed: {e}", exc_info=True)


def _log_refresh(doc_count: int, chunk_count: int):
    """Log refresh metadata to SQLite."""
    import aiosqlite

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


def start_scheduler():
    """Register scheduled jobs. Called from FastAPI lifespan."""
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        refresh_knowledge_base,
        "cron",
        hour=settings.KB_REFRESH_CRON_HOUR,
        minute=0,
        id="kb_daily_refresh",
        replace_existing=True,
    )
    # Extra Monday refresh to cover weekend earnings releases
    scheduler.add_job(
        refresh_knowledge_base,
        "cron",
        day_of_week="mon",
        hour=3,
        minute=0,
        id="kb_weekly_refresh",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("APScheduler started — knowledge base refresh jobs registered")
    return scheduler


# ── CLI manual trigger ────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Knowledge base refresh utility")
    parser.add_argument(
        "--run-now", action="store_true", help="Immediately run a full refresh"
    )
    args = parser.parse_args()
    if args.run_now:
        refresh_knowledge_base()
    else:
        print("Use --run-now to trigger an immediate refresh")
