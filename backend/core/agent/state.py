"""Agent state schema for LangGraph ReAct agent."""

from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Extended state with financial-domain fields."""

    remaining_steps: int = 25       # Required by create_react_agent (recursion limit)
    ticker: str | None = None       # 解析出的股票代码
    query_type: str | None = None   # market / rag / hybrid
    cache_hits: int = 0             # 缓存命中计数（日志用）
