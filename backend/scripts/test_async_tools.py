"""测试异步工具调用性能和错误处理"""

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
    """测试多个工具的并行执行"""
    
    agent = get_agent_with_coordinator()
    
    # 测试查询：需要调用多个工具
    test_query = "分析 AAPL：包括实时报价、基本面数据和技术指标"
    
    logger.info(f"\n{'='*60}")
    logger.info(f"测试查询: {test_query}")
    logger.info(f"{'='*60}\n")
    
    start_time = time.time()
    
    result = await agent.ainvoke({
        "messages": [HumanMessage(content=test_query)],
        "max_retries": 2,
    })
    
    elapsed = time.time() - start_time
    
    logger.info(f"\n{'='*60}")
    logger.info(f"执行完成，总耗时: {elapsed:.2f} 秒")
    logger.info(f"{'='*60}\n")
    
    # 打印最终回答
    final_message = result["messages"][-1]
    logger.info(f"最终回答:\n{final_message.content}\n")
    
    # 打印工具执行统计
    executed_tools = result.get("executed_tools", [])
    error_count = result.get("error_count", 0)
    
    if executed_tools:
        logger.info(f"已执行工具: {', '.join(executed_tools)}")
    if error_count > 0:
        logger.warning(f"工具执行错误数: {error_count}")
        logger.warning(f"最后错误: {result.get('last_error', 'N/A')}")


async def test_error_handling():
    """测试错误处理和重试机制"""
    
    agent = get_agent_with_coordinator()
    
    logger.info("\n" + "="*60)
    logger.info("测试: 错误处理和重试")
    logger.info("="*60)
    
    # 使用一个可能失败的查询
    test_query = "查询 INVALID_TICKER 的股价"
    
    start = time.time()
    result = await agent.ainvoke({
        "messages": [HumanMessage(content=test_query)],
        "max_retries": 2,
    })
    elapsed = time.time() - start
    
    logger.info(f"耗时: {elapsed:.2f}s")
    logger.info(f"错误计数: {result.get('error_count', 0)}")
    logger.info(f"最终回答: {result['messages'][-1].content[:200]}...")


async def test_timeout_handling():
    """测试超时控制"""
    
    agent = get_agent_with_coordinator()
    
    logger.info("\n" + "="*60)
    logger.info("测试: 超时控制")
    logger.info("="*60)
    
    # 查询多个工具，观察超时行为
    test_query = "全面分析 TSLA：报价、基本面、技术指标、财报、新闻"
    
    start = time.time()
    result = await agent.ainvoke({
        "messages": [HumanMessage(content=test_query)],
        "max_retries": 1,
    })
    elapsed = time.time() - start
    
    logger.info(f"总耗时: {elapsed:.2f}s")
    logger.info(f"执行的工具: {result.get('executed_tools', [])}")
    logger.info(f"错误数: {result.get('error_count', 0)}")


async def test_performance_comparison():
    """对比单个工具和多个工具的执行时间"""
    
    agent = get_agent_with_coordinator()
    
    # 测试1: 单个工具
    logger.info("\n" + "="*60)
    logger.info("性能对比测试")
    logger.info("="*60)
    
    logger.info("\n测试 1: 单个工具")
    start = time.time()
    result1 = await agent.ainvoke({
        "messages": [HumanMessage(content="AAPL 的当前价格是多少？")],
    })
    time1 = time.time() - start
    logger.info(f"单工具耗时: {time1:.2f}s")
    
    # 测试2: 多个工具（应该并行执行）
    logger.info("\n测试 2: 多个工具并行")
    start = time.time()
    result2 = await agent.ainvoke({
        "messages": [HumanMessage(content="分析 AAPL：报价、基本面、技术指标")],
    })
    time2 = time.time() - start
    logger.info(f"多工具并行耗时: {time2:.2f}s")
    
    # 分析性能提升
    logger.info("\n" + "="*60)
    logger.info("性能分析")
    logger.info("="*60)
    logger.info(f"单工具: {time1:.2f}s")
    logger.info(f"多工具: {time2:.2f}s")
    
    if time2 < time1 * 2.5:  # 如果多工具时间小于单工具的2.5倍
        speedup = (time1 * 3) / time2
        logger.info(f"✓ 并行执行有效！")
        logger.info(f"  理论串行: ~{time1 * 3:.2f}s")
        logger.info(f"  实际并行: {time2:.2f}s")
        logger.info(f"  性能提升: ~{speedup:.1f}x")
    else:
        logger.warning(f"⚠ 并行效果不明显")


async def main():
    """主测试函数"""
    
    logger.info("\n" + "="*60)
    logger.info("异步工具调用优化测试")
    logger.info("="*60 + "\n")
    
    try:
        # 测试1: 基本并行执行
        await test_parallel_execution()
        await asyncio.sleep(2)
        
        # 测试2: 错误处理
        await test_error_handling()
        await asyncio.sleep(2)
        
        # 测试3: 超时控制
        await test_timeout_handling()
        await asyncio.sleep(2)
        
        # 测试4: 性能对比
        await test_performance_comparison()
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
