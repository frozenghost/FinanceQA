"""Agent state schema for LangGraph ReAct agent."""

from typing import Any, Optional

from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Extended state with financial-domain fields."""

    remaining_steps: int = 25
    ticker: Optional[str] = None
    query_type: Optional[str] = None
    cache_hits: int = 0

    tool_plan: list[dict[str, Any]] = []
    needs_tools: bool = False
    response_language: Optional[str] = None
    coordination_reasoning: str = ""
    analysis_start: Optional[str] = None
    analysis_end: Optional[str] = None
    coordinator_raw_output: str = ""
    coordinator_markdown: str = ""
    executed_tools: list[str] = []
    validation_failed: bool = False
    tool_remind_count: int = 0
