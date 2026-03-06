"""Admin endpoints for knowledge base management and model evaluation."""

import asyncio
import json
import logging
from pathlib import Path
from threading import Thread

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from config.settings import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def _verify_admin_token(authorization: str):
    pass
    # """Verify admin token from Authorization header."""
    # token = authorization.replace("Bearer ", "").strip()
    # if token != settings.ADMIN_TOKEN:
    #     raise HTTPException(status_code=403, detail="Invalid admin token")


@router.post("/admin/refresh-knowledge")
async def refresh_knowledge(
    authorization: str = Header(default=""),
):
    """Manually trigger knowledge base refresh."""
    _verify_admin_token(authorization)

    try:
        from scripts.refresh_knowledge import refresh_knowledge_base

        # Run in background thread to avoid blocking the API
        thread = Thread(target=refresh_knowledge_base, daemon=True)
        thread.start()

        return {
            "status": "started",
            "message": "Knowledge base refresh started; check backend logs for progress",
        }
    except Exception as e:
        logger.error(f"Knowledge base refresh failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class EvalRequest(BaseModel):
    models: list[str]
    compare: bool = True


@router.post("/admin/evaluate-models")
async def evaluate_models(
    request: EvalRequest,
    authorization: str = Header(default=""),
):
    """Trigger model quality evaluation and comparison.

    Example:
        POST /admin/evaluate-models
        Body: {"models": ["anthropic/claude-opus-4.6", "openai/gpt-4o"], "compare": true}
    """
    _verify_admin_token(authorization)

    if not request.models:
        raise HTTPException(status_code=400, detail="At least one model is required")

    def _run_evaluation():
        from scripts.evaluate_model import ModelEvaluator

        evaluator = ModelEvaluator()
        reports = []

        for model in request.models:
            try:
                report = asyncio.run(evaluator.evaluate_model(model))
                evaluator.save_report(report)
                reports.append(report)
                logger.info(
                    f"Evaluation complete for {model}: "
                    f"{report['summary']['overall_score']}/10"
                )
            except Exception as e:
                logger.error(f"Evaluation failed for {model}: {e}")

        if request.compare and len(reports) >= 2:
            try:
                comparison = evaluator.generate_comparison(reports)
                evaluator.save_comparison(comparison)
                logger.info(f"Comparison report generated: {comparison['verdict']}")
            except Exception as e:
                logger.error(f"Comparison generation failed: {e}")

    thread = Thread(target=_run_evaluation, daemon=True)
    thread.start()

    return {
        "status": "started",
        "message": f"Model evaluation started; evaluating {len(request.models)} model(s)",
        "models": request.models,
        "compare": request.compare,
        "reports_dir": settings.EVAL_REPORTS_DIR,
    }


@router.get("/admin/eval-reports")
async def list_eval_reports(
    authorization: str = Header(default=""),
):
    """List available evaluation reports."""
    _verify_admin_token(authorization)

    reports_dir = Path(settings.EVAL_REPORTS_DIR)
    if not reports_dir.exists():
        return {"reports": []}

    reports = []
    for f in sorted(reports_dir.glob("*.json"), reverse=True):
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            if "meta" in data:
                reports.append(
                    {
                        "filename": f.name,
                        "type": "comparison" if "ranking" in data else "evaluation",
                        "model": data["meta"].get("model", "N/A"),
                        "models": data["meta"].get("models", []),
                        "evaluated_at": data["meta"].get(
                            "evaluated_at", data["meta"].get("compared_at", "")
                        ),
                        "overall_score": data.get("summary", {}).get(
                            "overall_score", None
                        ),
                        "verdict": data.get("verdict", ""),
                    }
                )
        except Exception:
            continue

    return {"reports": reports}


@router.get("/admin/health")
async def health_check():
    """Basic health check endpoint."""
    from services.cache_service import REDIS_AVAILABLE

    return {
        "status": "ok",
        "redis": "connected" if REDIS_AVAILABLE else "degraded",
    }
