"""LangGraph ReAct Agent — uses prebuilt create_react_agent."""

from langgraph.prebuilt import create_react_agent

from core.agent.state import AgentState
from prompts.loader import load_system_prompt
from services.llm_client import LLMClient
from skills import ALL_TOOLS
from config.settings import settings


def build_agent():
    """Build and return a LangGraph ReAct agent."""
    llm = LLMClient().get_langchain_model(role="market_analyst")

    # Use prebuilt agent — no hand-written nodes or edges
    agent = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        state_schema=AgentState,
        prompt=load_system_prompt(),
    )
    return agent


# Lazy singleton
_agent = None


def get_agent():
    """
    Get or create the singleton agent instance.
    
    根据配置选择使用标准模式或协调器模式：
    - USE_COORDINATOR=True: 使用协调器模式（强制工具使用，减少幻觉）
    - USE_COORDINATOR=False: 使用标准 ReAct 模式
    """
    global _agent
    if _agent is None:
        if settings.USE_COORDINATOR:
            # 使用协调器模式
            from core.agent.graph_with_coordinator import get_agent_with_coordinator
            _agent = get_agent_with_coordinator()
        else:
            # 使用标准模式
            _agent = build_agent()
    return _agent
