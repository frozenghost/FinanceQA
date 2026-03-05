"""Agent state schema for LangGraph ReAct agent."""

from typing import Any
from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Extended state with financial-domain fields."""

    remaining_steps: int = 25       # Required by create_react_agent (recursion limit)
    ticker: str | None = None       # 解析出的股票代码
    query_type: str | None = None   # market / rag / hybrid
    cache_hits: int = 0             # 缓存命中计数（日志用）
    
    # 协调器相关字段
    tool_plan: list[dict[str, Any]] = []  # 工具调用计划
    needs_tools: bool = False              # 是否需要工具
    coordination_reasoning: str = ""       # 协调推理过程
    coordinator_raw_output: str = ""       # 协调器原始输出
    executed_tools: list[str] = []         # 已执行的工具列表
    validation_failed: bool = False        # 验证是否失败
    retry_count: int = 0                   # 重试次数
