"""
LangGraph Agent with Coordinator - Force tool usage, reduce hallucinations

Architecture:
1. coordinator: Analyze question, plan tool calls
2. enforcer: Force tool usage
3. agent: Execute tool calls and generate answer
4. tools: Execute tools in parallel (async + error handling)
5. error_handler: Handle tool execution failures
"""

import asyncio
import logging
import time
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from core.agent.state import AgentState
from core.agent.coordinator import (
    coordinator_chain,
    should_use_tools,
    enforce_tool_usage,
    validate_tool_execution,
)
from prompts.loader import load_system_prompt
from services.llm_client import LLMClient
from skills import ALL_TOOLS

logger = logging.getLogger(__name__)


async def agent_node(state: AgentState) -> dict:
    """Agent node: Call LLM for reasoning and tool calling"""
    llm = LLMClient().get_langchain_model(role="market_analyst")
    
    # Bind tools, enable parallel tool calls
    llm_with_tools = llm.bind_tools(ALL_TOOLS, parallel_tool_calls=True)
    
    # Get system prompt (only add on first call)
    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) and "You are a professional" in m.content for m in messages):
        # Use strict mode prompt
        system_prompt = load_system_prompt(strict=True)
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


def track_executed_tools(state: AgentState) -> dict:
    """Track executed tools"""
    messages = state["messages"]
    executed_tools = []
    seen = set()
    
    # Iterate through all messages, collect executed tools (deduplicated, keeping params)
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
    
    # Compare plan vs actual execution
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


def should_continue(state: AgentState) -> Literal["tools", "end"]:
    """
    Decide next step:
    - If there are tool calls → execute tools
    - Otherwise → end
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    # If there are tool calls, execute tools
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    
    return "end"


async def enhanced_tool_node(state: AgentState) -> dict:
    """Enhanced tool execution node: with timeout, error handling, and performance monitoring"""
    messages = state["messages"]
    last_message = messages[-1]
    
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return state
    
    tool_calls = last_message.tool_calls
    logger.info(f"[enhanced_tool_node] Starting parallel execution of {len(tool_calls)} tools")
    
    start_time = time.time()
    tool_messages = []
    
    async def execute_single_tool(tool_call):
        """Execute single tool with timeout and error handling"""
        tool_name = tool_call.get("name", "unknown")
        tool_id = tool_call.get("id", "")
        
        try:
            # Find tool
            tool = next((t for t in ALL_TOOLS if t.name == tool_name), None)
            if not tool:
                return ToolMessage(
                    content=f"Error: Tool '{tool_name}' does not exist",
                    tool_call_id=tool_id
                )
            
            # Execute tool with 30s timeout
            logger.info(f"[tool:{tool_name}] Starting execution")
            tool_start = time.time()
            
            result = await asyncio.wait_for(
                tool.ainvoke(tool_call.get("args", {})),
                timeout=30.0
            )
            
            tool_elapsed = time.time() - tool_start
            logger.info(f"[tool:{tool_name}] Completed in {tool_elapsed:.2f}s")
            
            return ToolMessage(
                content=str(result),
                tool_call_id=tool_id
            )
            
        except asyncio.TimeoutError:
            logger.error(f"[tool:{tool_name}] Execution timeout (>30s)")
            return ToolMessage(
                content=f"Error: Tool '{tool_name}' execution timeout",
                tool_call_id=tool_id
            )
        except Exception as e:
            logger.error(f"[tool:{tool_name}] Execution failed: {e}", exc_info=True)
            return ToolMessage(
                content=f"Error: Tool '{tool_name}' execution failed - {str(e)}",
                tool_call_id=tool_id
            )
    
    # Execute all tools in parallel
    tool_messages = await asyncio.gather(
        *[execute_single_tool(tc) for tc in tool_calls],
        return_exceptions=False
    )
    
    total_elapsed = time.time() - start_time
    logger.info(f"[enhanced_tool_node] All tools executed, total time {total_elapsed:.2f}s")

    return {"messages": list(tool_messages)}


def error_handler_node(state: AgentState) -> dict:
    """Error handler node: Analyze tool execution failures and record failed tools"""
    messages = state["messages"]
    error_count = state.get("error_count", 0)
    failed_tools = state.get("failed_tools", [])
    
    # Check recent tool messages for errors and record failed tool names
    tool_errors = []
    new_failed_tools = []
    
    # Find the last AIMessage's tool_calls
    last_ai_message = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            last_ai_message = msg
            break
    
    if last_ai_message:
        # Check each tool call result
        for tool_call in last_ai_message.tool_calls:
            tool_name = tool_call.get("name", "")
            tool_id = tool_call.get("id", "")
            
            # Find corresponding ToolMessage
            tool_msg = next(
                (m for m in reversed(messages) 
                 if isinstance(m, ToolMessage) and m.tool_call_id == tool_id),
                None
            )
            
            if tool_msg and "Error" in tool_msg.content:
                tool_errors.append(tool_msg.content)
                if tool_name not in failed_tools:
                    new_failed_tools.append(tool_name)
    
    if tool_errors:
        logger.warning(f"[error_handler] Detected {len(tool_errors)} tool errors")
        for err in tool_errors:
            logger.warning(f"  - {err}")
    
    return {
        "error_count": error_count + len(tool_errors),
        "last_error": tool_errors[0] if tool_errors else None,
        "failed_tools": failed_tools + new_failed_tools,
    }


async def retry_failed_tools_node(state: AgentState) -> dict:
    """Retry failed tools node: Only re-execute failed tools"""
    messages = state["messages"]
    failed_tools = state.get("failed_tools", [])
    
    if not failed_tools:
        return state
    
    logger.info(f"[retry_failed_tools] Retrying {len(failed_tools)} failed tools: {', '.join(failed_tools)}")
    
    # Find the last AIMessage's tool_calls
    last_ai_message = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            last_ai_message = msg
            break
    
    if not last_ai_message:
        return state
    
    # Only retry failed tools
    failed_tool_calls = [
        tc for tc in last_ai_message.tool_calls
        if tc.get("name", "") in failed_tools
    ]
    
    if not failed_tool_calls:
        return state
    
    logger.info(f"[retry_failed_tools] Starting retry of {len(failed_tool_calls)} tool calls")
    start_time = time.time()
    
    async def execute_single_tool(tool_call):
        """Execute single tool with timeout and error handling"""
        tool_name = tool_call.get("name", "unknown")
        tool_id = tool_call.get("id", "")
        
        try:
            # Find tool
            tool = next((t for t in ALL_TOOLS if t.name == tool_name), None)
            if not tool:
                return ToolMessage(
                    content=f"Error: Tool '{tool_name}' does not exist",
                    tool_call_id=tool_id
                )
            
            # Execute tool with 30s timeout
            logger.info(f"[tool:{tool_name}] Retrying execution")
            tool_start = time.time()
            
            result = await asyncio.wait_for(
                tool.ainvoke(tool_call.get("args", {})),
                timeout=30.0
            )
            
            tool_elapsed = time.time() - tool_start
            logger.info(f"[tool:{tool_name}] Retry completed in {tool_elapsed:.2f}s")
            
            return ToolMessage(
                content=str(result),
                tool_call_id=tool_id
            )
            
        except asyncio.TimeoutError:
            logger.error(f"[tool:{tool_name}] Retry timeout (>30s)")
            return ToolMessage(
                content=f"Error: Tool '{tool_name}' execution timeout",
                tool_call_id=tool_id
            )
        except Exception as e:
            logger.error(f"[tool:{tool_name}] Retry failed: {e}", exc_info=True)
            return ToolMessage(
                content=f"Error: Tool '{tool_name}' execution failed - {str(e)}",
                tool_call_id=tool_id
            )
    
    # Retry all failed tools in parallel
    retry_messages = await asyncio.gather(
        *[execute_single_tool(tc) for tc in failed_tool_calls],
        return_exceptions=False
    )
    
    total_elapsed = time.time() - start_time
    logger.info(f"[retry_failed_tools] Retry completed, total time {total_elapsed:.2f}s")
    
    # Replace original failed ToolMessage
    updated_messages = []
    retry_msg_dict = {msg.tool_call_id: msg for msg in retry_messages}
    
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.tool_call_id in retry_msg_dict:
            # Replace with retry message
            updated_messages.append(retry_msg_dict[msg.tool_call_id])
        else:
            updated_messages.append(msg)
    
    return {
        "messages": updated_messages,
        "failed_tools": [],  # Clear failed tools list
    }


def should_retry(state: AgentState) -> Literal["retry", "continue"]:
    """Decide whether to retry failed tools"""
    error_count = state.get("error_count", 0)
    max_retries = state.get("max_retries", 2)
    failed_tools = state.get("failed_tools", [])
    
    # Only retry when there are failed tools and not exceeding retry limit
    if failed_tools and error_count < max_retries:
        logger.info(f"[should_retry] Will retry failed tools: {', '.join(failed_tools)} (attempt {error_count + 1}/{max_retries})")
        return "retry"
    
    if failed_tools and error_count >= max_retries:
        logger.warning(f"[should_retry] Max retry attempts reached, giving up: {', '.join(failed_tools)}")
    
    return "continue"


def build_agent_with_coordinator():
    """Build Agent with Coordinator
    
    Optimizations:
    1. Async parallel tool execution (asyncio.gather)
    2. Timeout control (30s/tool)
    3. Error handling and retry mechanism
    4. Performance monitoring and logging
    """
    
    # Create state graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("coordinator", coordinator_chain)           # Coordinator: plan tools (LCEL for streaming)
    workflow.add_node("enforcer", enforce_tool_usage)           # Enforcer: add enforcement instructions
    workflow.add_node("agent", agent_node)                      # Agent: LLM reasoning (async)
    workflow.add_node("tools", enhanced_tool_node)              # Tools execution (enhanced)
    workflow.add_node("error_handler", error_handler_node)      # Error handling
    workflow.add_node("retry_tools", retry_failed_tools_node)   # Retry failed tools
    workflow.add_node("tracker", track_executed_tools)          # Tracker: track executed tools
    workflow.add_node("validator", validate_tool_execution)     # Validator: compare plan vs execution
    
    # Set entry point
    workflow.set_entry_point("coordinator")
    
    # Coordinator → router (whether tools are needed)
    workflow.add_conditional_edges(
        "coordinator",
        should_use_tools,
        {
            "use_tools": "enforcer",      # Need tools → enforcer
            "direct_answer": "agent",     # No tools needed → direct answer
        }
    )
    
    # Enforcer → Agent
    workflow.add_edge("enforcer", "agent")
    
    # Agent → conditional router
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",         # Has tool calls → parallel execute
            "end": "tracker",         # End → tracker (statistics)
        }
    )
    
    # After tool execution → error handling
    workflow.add_edge("tools", "error_handler")
    
    # Error handling → conditional router (retry or continue)
    workflow.add_conditional_edges(
        "error_handler",
        should_retry,
        {
            "retry": "retry_tools",   # Retry → only retry failed tools
            "continue": "agent",      # Continue → return to Agent (with error info)
        }
    )
    
    # After retry tools → return to Agent
    workflow.add_edge("retry_tools", "agent")
    
    # Tracker → Validator → End
    workflow.add_edge("tracker", "validator")
    workflow.add_edge("validator", END)
    
    return workflow.compile()


# Lazy load singleton
_agent_with_coordinator = None


def get_agent_with_coordinator():
    """Get or create agent with coordinator instance"""
    global _agent_with_coordinator
    if _agent_with_coordinator is None:
        _agent_with_coordinator = build_agent_with_coordinator()
    return _agent_with_coordinator
