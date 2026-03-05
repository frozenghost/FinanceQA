"""LangGraph ReAct Agent — uses prebuilt create_react_agent."""

from langchain.agents import create_agent

from core.agent.state import AgentState
from prompts.loader import load_system_prompt
from services.llm_client import LLMClient
from skills import ALL_TOOLS
from config.settings import settings


def build_agent():
    """Build and return a LangGraph ReAct agent."""
    llm = LLMClient().get_langchain_model(role="market_analyst")

    # Use prebuilt agent — no hand-written nodes or edges
    agent = create_agent(
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
    
    Choose between standard mode or coordinator mode based on configuration:
    - USE_COORDINATOR=True: Use coordinator mode (force tool usage, reduce hallucinations)
    - USE_COORDINATOR=False: Use standard ReAct mode
    """
    global _agent
    if _agent is None:
        if settings.USE_COORDINATOR:
            # Use coordinator mode
            from core.agent.graph_with_coordinator import get_agent_with_coordinator
            _agent = get_agent_with_coordinator()
        else:
            # Use standard mode
            _agent = build_agent()
    return _agent
