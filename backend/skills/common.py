"""Shared utilities and validators for skills."""

import asyncio
import re
from typing import Any, Callable, TypeVar

# Date and interval constants reused by market_data and technical_analysis
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALID_INTERVALS = ("1d", "1wk", "1mo")
VALID_PERIODS = ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max")

T = TypeVar("T")


def validate_non_empty(value: str, field_name: str = "value") -> str:
    """Strip and validate non-empty string; raise ValueError if empty."""
    stripped = (value or "").strip()
    if not stripped:
        raise ValueError(f"{field_name} must be non-empty")
    return stripped


async def run_sync(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a synchronous callable in a thread pool (avoids blocking the event loop)."""
    return await asyncio.to_thread(fn, *args, **kwargs)
