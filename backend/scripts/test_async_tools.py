"""Test async tool execution performance and error handling."""

import asyncio
import time
import logging
from langchain_core.messages import HumanMessage

from core.agent.graph_with_coordinator import get_agent_with_coordinator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_parallel_execution():
    """Test parallel execution of multiple tools."""

    agent = get_agent_with_coordinator()

    test_query = "Analyze AAPL: real-time quote, fundamentals, and technical indicators"

    logger.info(f"\n{'='*60}")
    logger.info(f"Test query: {test_query}")
    logger.info(f"{'='*60}\n")

    start_time = time.time()

    result = await agent.ainvoke({
        "messages": [HumanMessage(content=test_query)],
        "max_retries": 2,
    })

    elapsed = time.time() - start_time

    logger.info(f"\n{'='*60}")
    logger.info(f"Done. Total time: {elapsed:.2f}s")
    logger.info(f"{'='*60}\n")

    final_message = result["messages"][-1]
    logger.info(f"Final answer:\n{final_message.content}\n")

    executed_tools = result.get("executed_tools", [])
    error_count = result.get("error_count", 0)

    if executed_tools:
        logger.info(f"Executed tools: {', '.join(executed_tools)}")
    if error_count > 0:
        logger.warning(f"Tool errors: {error_count}")
        logger.warning(f"Last error: {result.get('last_error', 'N/A')}")


async def test_error_handling():
    """Test error handling and retry."""
    agent = get_agent_with_coordinator()

    logger.info("\n" + "="*60)
    logger.info("Test: error handling and retry")
    logger.info("="*60)

    test_query = "What is the stock price of INVALID_TICKER?"

    start = time.time()
    result = await agent.ainvoke({
        "messages": [HumanMessage(content=test_query)],
        "max_retries": 2,
    })
    elapsed = time.time() - start

    logger.info(f"Time: {elapsed:.2f}s")
    logger.info(f"Error count: {result.get('error_count', 0)}")
    logger.info(f"Final answer: {result['messages'][-1].content[:200]}...")


async def test_timeout_handling():
    """Test timeout handling."""
    agent = get_agent_with_coordinator()

    logger.info("\n" + "="*60)
    logger.info("Test: timeout control")
    logger.info("="*60)

    test_query = "Full analysis of TSLA: quote, fundamentals, technicals, earnings, news"

    start = time.time()
    result = await agent.ainvoke({
        "messages": [HumanMessage(content=test_query)],
        "max_retries": 1,
    })
    elapsed = time.time() - start

    logger.info(f"Total time: {elapsed:.2f}s")
    logger.info(f"Executed tools: {result.get('executed_tools', [])}")
    logger.info(f"Errors: {result.get('error_count', 0)}")


async def test_performance_comparison():
    """Compare single-tool vs multi-tool execution time."""
    agent = get_agent_with_coordinator()

    logger.info("\n" + "="*60)
    logger.info("Performance comparison")
    logger.info("="*60)

    logger.info("\nTest 1: single tool")
    start = time.time()
    result1 = await agent.ainvoke({
        "messages": [HumanMessage(content="What is AAPL's current price?")],
    })
    time1 = time.time() - start
    logger.info(f"Single tool: {time1:.2f}s")

    logger.info("\nTest 2: multiple tools (parallel)")
    start = time.time()
    result2 = await agent.ainvoke({
        "messages": [HumanMessage(content="Analyze AAPL: quote, fundamentals, technicals")],
    })
    time2 = time.time() - start
    logger.info(f"Multi-tool: {time2:.2f}s")

    logger.info("\n" + "="*60)
    logger.info("Analysis")
    logger.info("="*60)
    logger.info(f"Single: {time1:.2f}s")
    logger.info(f"Multi: {time2:.2f}s")

    if time2 < time1 * 2.5:
        speedup = (time1 * 3) / time2
        logger.info("✓ Parallel execution effective")
        logger.info(f"  Theoretical serial: ~{time1 * 3:.2f}s")
        logger.info(f"  Actual parallel: {time2:.2f}s")
        logger.info(f"  Speedup: ~{speedup:.1f}x")
    else:
        logger.warning("⚠ Parallel benefit not obvious")


async def main():
    """Main test entry."""
    logger.info("\n" + "="*60)
    logger.info("Async tool execution tests")
    logger.info("="*60 + "\n")

    try:
        await test_parallel_execution()
        await asyncio.sleep(2)

        await test_error_handling()
        await asyncio.sleep(2)

        await test_timeout_handling()
        await asyncio.sleep(2)

        await test_performance_comparison()

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
