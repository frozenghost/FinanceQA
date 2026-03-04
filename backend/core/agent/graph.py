"""LangGraph ReAct Agent — uses prebuilt create_react_agent."""

from langgraph.prebuilt import create_react_agent

from core.agent.state import AgentState
from prompts.loader import load_system_prompt
from services.llm_client import LLMClient
from skills import ALL_TOOLS


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
    """Get or create the singleton agent instance."""
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent
