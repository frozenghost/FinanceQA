"""Test coordinator tool-call consistency."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import HumanMessage
from core.agent.graph_with_coordinator import get_agent_with_coordinator


def _executed_tool_names(executed_tools):
    """Normalize executed_tools to list of tool names (state may store list of dicts)."""
    if not executed_tools:
        return []
    first = executed_tools[0]
    if isinstance(first, dict):
        return [t.get("tool", "") for t in executed_tools if t.get("tool")]
    return list(executed_tools)


async def test_coordinator_consistency():
    """Test that coordinator plan matches actual execution."""

    test_cases = [
        {
            "name": "Single tool",
            "query": "What is AAPL's price now?",
            "expected_tools": ["get_real_time_quote"],
        },
        {
            "name": "Multi-tool - fundamentals + technicals",
            "query": "Analyze TSLA fundamentals and technicals",
            "expected_tools": ["get_company_fundamentals", "calculate_technical_indicators"],
        },
        {
            "name": "Composite - price + news + technicals",
            "query": "How is BABA doing lately? Include price, news and technicals",
            "expected_tools": ["get_real_time_quote", "get_financial_news", "calculate_technical_indicators"],
        },
    ]

    agent = get_agent_with_coordinator()

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'='*80}")
        print(f"Test {i}: {test_case['name']}")
        print(f"Query: {test_case['query']}")
        print(f"Expected tools: {', '.join(test_case['expected_tools'])}")
        print(f"{'='*80}\n")

        state = {"messages": [HumanMessage(content=test_case["query"])]}

        try:
            result = await agent.ainvoke(state)

            executed_raw = result.get("executed_tools", [])
            executed_tools = _executed_tool_names(executed_raw)
            tool_plan = result.get("tool_plan", [])
            planned_tools = [t["tool"] for t in tool_plan]

            print(f"Coordinator plan: {', '.join(planned_tools) if planned_tools else 'none'}")
            print(f"Executed: {', '.join(executed_tools) if executed_tools else 'none'}")

            if set(planned_tools) == set(executed_tools):
                print("Consistency: pass")
            else:
                missing = set(planned_tools) - set(executed_tools)
                extra = set(executed_tools) - set(planned_tools)
                print("Consistency: fail")
                if missing:
                    print(f"  Missing: {', '.join(missing)}")
                if extra:
                    print(f"  Extra: {', '.join(extra)}")

            final_message = result["messages"][-1]
            if hasattr(final_message, "content"):
                print(f"\nFinal answer:\n{final_message.content[:200]}...")

        except Exception as e:
            print(f"Execution failed: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_coordinator_consistency())
