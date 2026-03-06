"""Agent state schema for LangGraph ReAct agent."""

from typing import Any
from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Extended state with financial-domain fields."""

    remaining_steps: int = 25
    ticker: str | None = None
    query_type: str | None = None
    cache_hits: int = 0
    
    tool_plan: list[dict[str, Any]] = []
    needs_tools: bool = False
    response_language: str | None = None
    coordination_reasoning: str = ""
    coordinator_raw_output: str = ""
    coordinator_markdown: str = ""
    executed_tools: list[str] = []
    validation_failed: bool = False
    tool_remind_count: int = 0
