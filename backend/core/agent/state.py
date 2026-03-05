"""Agent state schema for LangGraph ReAct agent."""

from typing import Any
from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Extended state with financial-domain fields."""

    remaining_steps: int = 25       # Required by create_react_agent (recursion limit)
    ticker: str | None = None       # Parsed stock ticker
    query_type: str | None = None   # market / rag / hybrid
    cache_hits: int = 0             # Cache hit counter
    
    # Coordinator related fields
    tool_plan: list[dict[str, Any]] = []  # Tool call plan
    needs_tools: bool = False              # Whether tools are needed
    coordination_reasoning: str = ""       # Coordinator reasoning process
    coordinator_raw_output: str = ""       # Coordinator raw output (full)
    coordinator_markdown: str = ""         # Coordinator Markdown output (display only)
    executed_tools: list[str] = []         # List of executed tools
    validation_failed: bool = False        # Validation status
    retry_count: int = 0                   # Retry count
    
    # Error handling and performance monitoring
    error_count: int = 0                   # Tool execution error counter
    max_retries: int = 2                   # Maximum retry attempts
    last_error: str | None = None          # Last error message
    failed_tools: list[str] = []           # Failed tools list
    tool_execution_times: dict[str, float] = {}  # Tool execution time statistics
