"""
LangGraph Agent with Coordinator - Force tool usage, reduce hallucinations

Architecture:
1. coordinator: Analyze question, plan tool calls
2. enforcer: Force tool usage
3. agent: Execute tool calls and generate answer
4. tools: Execute tools in parallel (ToolNode with RetryPolicy)
"""

import logging
from typing import Literal

MAX_TOOL_REMIND = 2
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.types import RetryPolicy
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import AIMessage, SystemMessage

from core.agent.state import AgentState
from core.agent.coordinator import (
    coordinator_node,
    should_use_tools,
    enforce_tool_usage,
    validate_tool_execution,
)
from prompts.loader import load_system_prompt
from services.llm_client import LLMClient
from skills import ALL_TOOLS

logger = logging.getLogger(__name__)

# ToolNode with built-in parallel execution, timeout, and error handling
tool_node = ToolNode(ALL_TOOLS)

# Retry policy for tool execution
tool_retry_policy = RetryPolicy(
    max_attempts=2,
    initial_interval=1.0,
    backoff_factor=2.0,
    retry_on=(Exception,),
)

# Checkpointer for durable execution
checkpointer = InMemorySaver()


RESPONSE_LANGUAGE_NAMES = {
    "zh": "Chinese (Simplified)",
    "zh-Hans": "Chinese (Simplified)",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
}


async def agent_node(state: AgentState) -> dict:
    """Agent node: Call LLM for reasoning and tool calling"""
    llm = LLMClient().get_langchain_model(role="market_analyst")
    llm_with_tools = llm.bind_tools(ALL_TOOLS, parallel_tool_calls=True)

    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) and "You are a professional" in m.content for m in messages):
        system_prompt = load_system_prompt(strict=True)
        lang_code = state.get("response_language") or "en"
        lang_name = RESPONSE_LANGUAGE_NAMES.get(lang_code) or lang_code
        system_prompt += f"\n\n**Response language**: You must respond in **{lang_name}**. (Detected from user question: {lang_code})"
        messages = [SystemMessage(content=system_prompt)] + messages

    logger.info("[agent_node] Calling LLM for reasoning")
    
    # Async call LLM
    response = await llm_with_tools.ainvoke(messages)
    
    # Check if there are tool calls
    if isinstance(response, AIMessage) and response.tool_calls:
        tool_names = [tc.get("name", "unknown") for tc in response.tool_calls]
        logger.info(f"[agent_node] LLM requested to call {len(tool_names)} tools: {', '.join(tool_names)}")
    else:
        logger.info("[agent_node] LLM generated final answer (no tool call)")
    
    return {"messages": [response]}


def _executed_tool_names_from_messages(messages: list) -> set:
    """Get set of tool names that have been requested (from AIMessage.tool_calls)."""
    seen = set()
    for msg in messages:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                name = tc.get("name", "") or ""
                if name:
                    seen.add(name)
    return seen


def track_executed_tools(state: AgentState) -> dict:
    """Track executed tools"""
    messages = state["messages"]
    executed_tools = []
    seen = set()

    for msg in messages:
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                tool_name = tool_call.get("name", "")
                if tool_name and tool_name not in seen:
                    seen.add(tool_name)
                    executed_tools.append(
                        {
                            "tool": tool_name,
                            "params": tool_call.get("args", {}) or {},
                        }
                    )

    tool_plan = state.get("tool_plan", [])
    if tool_plan:
        planned_tools = [t["tool"] for t in tool_plan]
        executed_names = [t["tool"] for t in executed_tools]
        logger.info("[tracker] Tool execution statistics:")
        logger.info(f"  Planned: {len(planned_tools)} - {', '.join(planned_tools)}")
        logger.info(f"  Executed: {len(executed_names)} - {', '.join(executed_names)}")

        missing = set(planned_tools) - set(executed_names)
        extra = set(executed_names) - set(planned_tools)

        if missing:
            logger.warning(f"  Missing: {', '.join(missing)}")
        if extra:
            logger.info(f"  Extra: {', '.join(extra)}")
        if not missing and not extra:
            logger.info("  ✓ Perfect match")

    return {"executed_tools": executed_tools}


def should_continue(state: AgentState) -> Literal["tools", "remind_missing", "end"]:
    """
    - If last message has tool_calls → execute tools.
    - If no tool_calls but planned tools are missing → remind and re-enter agent (cap at MAX_TOOL_REMIND).
    - Else → end.
    """
    messages = state["messages"]
    last_message = messages[-1]

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"

    tool_plan = state.get("tool_plan", []) or []
    if not tool_plan:
        return "end"

    executed = _executed_tool_names_from_messages(messages)
    planned = {t.get("tool", "") for t in tool_plan if t.get("tool")}
    missing = planned - executed
    remind_count = state.get("tool_remind_count", 0)

    if missing and remind_count < MAX_TOOL_REMIND:
        logger.info(f"[should_continue] Planned tools not all executed; reminding for: {', '.join(sorted(missing))}")
        return "remind_missing"
    return "end"


def remind_missing_tools(state: AgentState) -> dict:
    """Append a system message listing planned-but-not-executed tools and bump remind count."""
    messages = state["messages"]
    tool_plan = state.get("tool_plan", []) or []
    executed = _executed_tool_names_from_messages(messages)
    planned_names = [t.get("tool", "") for t in tool_plan if t.get("tool")]
    missing = sorted(set(planned_names) - executed)
    count = state.get("tool_remind_count", 0) + 1

    reminder = (
        f"⚠️ You have not yet called these tools from the plan: **{', '.join(missing)}**. "
        "You must call them now before giving a final answer. Do not answer until all planned tools are called."
    )
    return {"messages": [SystemMessage(content=reminder)], "tool_remind_count": count}


def build_agent_with_coordinator():
    """Build Agent with Coordinator
    
    Optimizations (using LangGraph built-in features):
    1. ToolNode: Parallel tool execution with timeout
    2. RetryPolicy: Automatic retry for failed tools
    3. InMemorySaver: Durable execution (checkpointing)
    """
    
    workflow = StateGraph(AgentState)
    
    workflow.add_node("coordinator", coordinator_node)
    workflow.add_node("enforcer", enforce_tool_usage)
    workflow.add_node("agent", agent_node)
    workflow.add_node(
        "tools",
        tool_node,
        retry=tool_retry_policy
    )
    workflow.add_node("tracker", track_executed_tools)
    workflow.add_node("validator", validate_tool_execution)
    workflow.add_node("remind_missing", remind_missing_tools)

    workflow.set_entry_point("coordinator")

    workflow.add_conditional_edges(
        "coordinator",
        should_use_tools,
        {
            "use_tools": "enforcer",
            "direct_answer": "agent",
        }
    )

    workflow.add_edge("enforcer", "agent")

    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "remind_missing": "remind_missing",
            "end": "tracker",
        }
    )

    workflow.add_edge("tools", "agent")
    workflow.add_edge("remind_missing", "agent")
    
    workflow.add_edge("tracker", "validator")
    workflow.add_edge("validator", END)
    
    return workflow.compile(checkpointer=checkpointer)


# Lazy load singleton
_agent_with_coordinator = None


def get_agent_with_coordinator():
    """Get or create agent with coordinator instance"""
    global _agent_with_coordinator
    if _agent_with_coordinator is None:
        _agent_with_coordinator = build_agent_with_coordinator()
    return _agent_with_coordinator
