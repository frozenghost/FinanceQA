"""Test selective retry: only failed tools are retried."""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from core.agent.state import AgentState

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Test tools
call_counts = {
    "tool_success": 0,
    "tool_fail_once": 0,
    "tool_always_fail": 0,
}


@tool
async def tool_success(query: str) -> dict:
    """Tool that always succeeds."""
    call_counts["tool_success"] += 1
    logger.info(f"[TEST] tool_success called (count {call_counts['tool_success']})")
    await asyncio.sleep(0.1)
    return {"result": "ok", "query": query}


@tool
async def tool_fail_once(query: str) -> dict:
    """Fails once then succeeds."""
    call_counts["tool_fail_once"] += 1
    logger.info(f"[TEST] tool_fail_once called (count {call_counts['tool_fail_once']})")
    await asyncio.sleep(0.1)

    if call_counts["tool_fail_once"] == 1:
        logger.warning("[TEST] tool_fail_once first call failed")
        return {"error": "first call failed"}
    else:
        logger.info("[TEST] tool_fail_once retry succeeded")
        return {"result": "retry ok", "query": query}


@tool
async def tool_always_fail(query: str) -> dict:
    """Tool that always fails."""
    call_counts["tool_always_fail"] += 1
    logger.info(f"[TEST] tool_always_fail called (count {call_counts['tool_always_fail']})")
    await asyncio.sleep(0.1)
    return {"error": "always fails"}


async def test_selective_retry():
    """Test: only failed tools are retried, successful tools are not re-executed."""

    logger.info("\n" + "="*60)
    logger.info("Test: selective retry")
    logger.info("="*60 + "\n")

    # Reset counters
    call_counts["tool_success"] = 0
    call_counts["tool_fail_once"] = 0
    
    # Build agent with test tools
    from langgraph.graph import StateGraph, END
    from langchain_core.messages import AIMessage, ToolMessage
    import time
    
    # Simplified agent node: return tool calls directly
    async def test_agent_node(state: AgentState) -> dict:
        """Test agent node: emit two tool calls."""
        logger.info("[test_agent_node] emitting tool calls")

        # Simulate LLM tool calls
        response = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "tool_success",
                    "args": {"query": "test1"},
                    "id": "call_1",
                },
                {
                    "name": "tool_fail_once",
                    "args": {"query": "test2"},
                    "id": "call_2",
                },
            ]
        )
        
        return {"messages": [response]}
    
    # Tool execution node
    async def test_tool_node(state: AgentState) -> dict:
        """Execute tools."""
        messages = state["messages"]
        last_message = messages[-1]

        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return state

        tool_calls = last_message.tool_calls
        logger.info(f"[test_tool_node] executing {len(tool_calls)} tools")
        
        tools_map = {
            "tool_success": tool_success,
            "tool_fail_once": tool_fail_once,
        }
        
        async def execute_tool(tc):
            tool_name = tc.get("name")
            tool_id = tc.get("id")
            tool_fn = tools_map.get(tool_name)
            
            if not tool_fn:
                return ToolMessage(
                    content=f"Error: tool '{tool_name}' not found",
                    tool_call_id=tool_id
                )
            
            try:
                result = await asyncio.wait_for(
                    tool_fn.ainvoke(tc.get("args", {})),
                    timeout=30.0
                )
                return ToolMessage(
                    content=str(result),
                    tool_call_id=tool_id
                )
            except Exception as e:
                return ToolMessage(
                    content=f"Error: {str(e)}",
                    tool_call_id=tool_id
                )
        
        tool_messages = await asyncio.gather(*[execute_tool(tc) for tc in tool_calls])
        return {"messages": list(tool_messages)}
    
    # Error handler node
    def test_error_handler(state: AgentState) -> dict:
        """Detect failed tools."""
        messages = state["messages"]
        error_count = state.get("error_count", 0)
        failed_tools = state.get("failed_tools", [])

        # Find last AIMessage
        last_ai_message = None
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                last_ai_message = msg
                break
        
        if not last_ai_message:
            return state
        
        # Check each tool result
        new_failed_tools = []
        for tc in last_ai_message.tool_calls:
            tool_name = tc.get("name")
            tool_id = tc.get("id")

            # Find corresponding ToolMessage
            tool_msg = next(
                (m for m in reversed(messages) 
                 if isinstance(m, ToolMessage) and m.tool_call_id == tool_id),
                None
            )
            
            if tool_msg:
                logger.info(f"[test_error_handler] check tool {tool_name}: {tool_msg.content[:50]}")
                # Check for 'error' in content (case-insensitive)
                if "'error'" in tool_msg.content.lower() or '"error"' in tool_msg.content.lower():
                    logger.warning(f"[test_error_handler] tool {tool_name} failed")
                    if tool_name not in failed_tools:
                        new_failed_tools.append(tool_name)
        
        logger.info(f"[test_error_handler] new failed tools: {new_failed_tools}")
        
        return {
            "error_count": error_count + len(new_failed_tools),
            "failed_tools": failed_tools + new_failed_tools,
        }
    
    # Retry node
    async def test_retry_node(state: AgentState) -> dict:
        """Retry only failed tools."""
        messages = state["messages"]
        failed_tools = state.get("failed_tools", [])

        if not failed_tools:
            return state

        logger.info(f"[test_retry_node] retrying failed tools: {failed_tools}")

        # Find last AIMessage
        last_ai_message = None
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                last_ai_message = msg
                break
        
        if not last_ai_message:
            return state
        
        # Retry only failed tools
        failed_tool_calls = [
            tc for tc in last_ai_message.tool_calls
            if tc.get("name") in failed_tools
        ]
        
        tools_map = {
            "tool_success": tool_success,
            "tool_fail_once": tool_fail_once,
        }
        
        async def execute_tool(tc):
            tool_name = tc.get("name")
            tool_id = tc.get("id")
            tool_fn = tools_map.get(tool_name)
            
            try:
                result = await asyncio.wait_for(
                    tool_fn.ainvoke(tc.get("args", {})),
                    timeout=30.0
                )
                return ToolMessage(
                    content=str(result),
                    tool_call_id=tool_id
                )
            except Exception as e:
                return ToolMessage(
                    content=f"Error: {str(e)}",
                    tool_call_id=tool_id
                )
        
        retry_messages = await asyncio.gather(*[execute_tool(tc) for tc in failed_tool_calls])
        
        # Replace original failed messages
        updated_messages = []
        retry_msg_dict = {msg.tool_call_id: msg for msg in retry_messages}
        
        for msg in messages:
            if isinstance(msg, ToolMessage) and msg.tool_call_id in retry_msg_dict:
                updated_messages.append(retry_msg_dict[msg.tool_call_id])
            else:
                updated_messages.append(msg)
        
        return {
            "messages": updated_messages,
            "failed_tools": [],
        }
    
    # Build test graph
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", test_agent_node)
    workflow.add_node("tools", test_tool_node)
    workflow.add_node("error_handler", test_error_handler)
    workflow.add_node("retry", test_retry_node)
    
    workflow.set_entry_point("agent")
    workflow.add_edge("agent", "tools")
    workflow.add_edge("tools", "error_handler")
    
    def should_retry(state: AgentState):
        failed_tools = state.get("failed_tools", [])
        error_count = state.get("error_count", 0)
        max_retries = state.get("max_retries", 2)
        
        if failed_tools and error_count < max_retries:
            return "retry"
        return "end"
    
    workflow.add_conditional_edges(
        "error_handler",
        should_retry,
        {
            "retry": "retry",
            "end": END,
        }
    )
    workflow.add_edge("retry", "error_handler")
    
    graph = workflow.compile()
    
    # Run test
    result = await graph.ainvoke({
        "messages": [HumanMessage(content="test")],
        "max_retries": 2,
    })
    
    logger.info("\n" + "="*60)
    logger.info("Test result")
    logger.info("="*60)

    logger.info("\nTool call counts:")
    logger.info(f"  tool_success: {call_counts['tool_success']} calls")
    logger.info(f"  tool_fail_once: {call_counts['tool_fail_once']} calls")

    success = True

    if call_counts['tool_success'] == 1:
        logger.info("✓ tool_success called 1 time (expected)")
    else:
        logger.error(f"✗ tool_success called {call_counts['tool_success']} times (expected 1)")
        success = False

    if call_counts['tool_fail_once'] == 2:
        logger.info("✓ tool_fail_once called 2 times (1 fail + 1 retry, expected)")
    else:
        logger.error(f"✗ tool_fail_once called {call_counts['tool_fail_once']} times (expected 2)")
        success = False

    logger.info(f"\nError count: {result.get('error_count', 0)}")
    logger.info(f"Failed tools: {result.get('failed_tools', [])}")

    logger.info("\n" + "="*60)
    if success:
        logger.info("✓ Pass: only failed tools were retried")
    else:
        logger.error("✗ Fail: retry logic did not match expectation")
    logger.info("="*60 + "\n")
    
    return success


async def main():
    """Main test entry."""

    logger.info("\n" + "="*60)
    logger.info("Selective retry test")
    logger.info("="*60 + "\n")

    try:
        test_passed = await test_selective_retry()

        logger.info("\n" + "="*60)
        logger.info("Summary")
        logger.info("="*60)
        logger.info(f"Selective retry: {'✓ pass' if test_passed else '✗ fail'}")
        logger.info("="*60 + "\n")

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
