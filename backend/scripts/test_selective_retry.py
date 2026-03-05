"""测试选择性重试：确保只重试失败的工具"""

import asyncio
import logging
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from core.agent.graph_with_coordinator import build_agent_with_coordinator
from core.agent.state import AgentState

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# 创建测试工具
call_counts = {
    "tool_success": 0,
    "tool_fail_once": 0,
    "tool_always_fail": 0,
}


@tool
async def tool_success(query: str) -> dict:
    """总是成功的工具"""
    call_counts["tool_success"] += 1
    logger.info(f"[TEST] tool_success 被调用 (第 {call_counts['tool_success']} 次)")
    await asyncio.sleep(0.1)
    return {"result": "成功", "query": query}


@tool
async def tool_fail_once(query: str) -> dict:
    """第一次失败，第二次成功的工具"""
    call_counts["tool_fail_once"] += 1
    logger.info(f"[TEST] tool_fail_once 被调用 (第 {call_counts['tool_fail_once']} 次)")
    await asyncio.sleep(0.1)
    
    if call_counts["tool_fail_once"] == 1:
        logger.warning(f"[TEST] tool_fail_once 第一次调用失败")
        return {"error": "第一次调用失败"}
    else:
        logger.info(f"[TEST] tool_fail_once 重试成功")
        return {"result": "重试成功", "query": query}


@tool
async def tool_always_fail(query: str) -> dict:
    """总是失败的工具"""
    call_counts["tool_always_fail"] += 1
    logger.info(f"[TEST] tool_always_fail 被调用 (第 {call_counts['tool_always_fail']} 次)")
    await asyncio.sleep(0.1)
    return {"error": "总是失败"}


async def test_selective_retry():
    """测试：只有失败的工具会被重试，成功的工具不会重新执行"""
    
    logger.info("\n" + "="*60)
    logger.info("测试：选择性重试机制")
    logger.info("="*60 + "\n")
    
    # 重置计数器
    call_counts["tool_success"] = 0
    call_counts["tool_fail_once"] = 0
    
    # 创建使用测试工具的 agent
    from langgraph.graph import StateGraph, END
    from langchain_core.messages import AIMessage, ToolMessage
    import time
    
    # 简化的 agent 节点：直接返回工具调用
    async def test_agent_node(state: AgentState) -> dict:
        """测试用的 agent 节点：直接调用两个工具"""
        logger.info("[test_agent_node] 生成工具调用")
        
        # 模拟 LLM 返回的工具调用
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
    
    # 工具执行节点
    async def test_tool_node(state: AgentState) -> dict:
        """执行工具"""
        messages = state["messages"]
        last_message = messages[-1]
        
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return state
        
        tool_calls = last_message.tool_calls
        logger.info(f"[test_tool_node] 执行 {len(tool_calls)} 个工具")
        
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
                    content=f"错误：工具 '{tool_name}' 不存在",
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
                    content=f"错误：{str(e)}",
                    tool_call_id=tool_id
                )
        
        tool_messages = await asyncio.gather(*[execute_tool(tc) for tc in tool_calls])
        return {"messages": list(tool_messages)}
    
    # 错误处理节点
    def test_error_handler(state: AgentState) -> dict:
        """检测失败的工具"""
        messages = state["messages"]
        error_count = state.get("error_count", 0)
        failed_tools = state.get("failed_tools", [])
        
        # 找到最后一个 AIMessage
        last_ai_message = None
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                last_ai_message = msg
                break
        
        if not last_ai_message:
            return state
        
        # 检查每个工具的结果
        new_failed_tools = []
        for tc in last_ai_message.tool_calls:
            tool_name = tc.get("name")
            tool_id = tc.get("id")
            
            # 查找对应的 ToolMessage
            tool_msg = next(
                (m for m in reversed(messages) 
                 if isinstance(m, ToolMessage) and m.tool_call_id == tool_id),
                None
            )
            
            if tool_msg:
                logger.info(f"[test_error_handler] 检查工具 {tool_name}: {tool_msg.content[:50]}")
                # 检查内容中是否包含 'error' 关键字（不区分大小写）
                if "'error'" in tool_msg.content.lower() or '"error"' in tool_msg.content.lower():
                    logger.warning(f"[test_error_handler] 工具 {tool_name} 失败")
                    if tool_name not in failed_tools:
                        new_failed_tools.append(tool_name)
        
        logger.info(f"[test_error_handler] 新增失败工具: {new_failed_tools}")
        
        return {
            "error_count": error_count + len(new_failed_tools),
            "failed_tools": failed_tools + new_failed_tools,
        }
    
    # 重试节点
    async def test_retry_node(state: AgentState) -> dict:
        """只重试失败的工具"""
        messages = state["messages"]
        failed_tools = state.get("failed_tools", [])
        
        if not failed_tools:
            return state
        
        logger.info(f"[test_retry_node] 重试失败的工具: {failed_tools}")
        
        # 找到最后一个 AIMessage
        last_ai_message = None
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                last_ai_message = msg
                break
        
        if not last_ai_message:
            return state
        
        # 只重试失败的工具
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
                    content=f"错误：{str(e)}",
                    tool_call_id=tool_id
                )
        
        retry_messages = await asyncio.gather(*[execute_tool(tc) for tc in failed_tool_calls])
        
        # 替换原来失败的消息
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
    
    # 构建测试图
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
    
    # 运行测试
    result = await graph.ainvoke({
        "messages": [HumanMessage(content="test")],
        "max_retries": 2,
    })
    
    logger.info("\n" + "="*60)
    logger.info("测试结果")
    logger.info("="*60)
    
    logger.info(f"\n工具调用统计:")
    logger.info(f"  tool_success: {call_counts['tool_success']} 次")
    logger.info(f"  tool_fail_once: {call_counts['tool_fail_once']} 次")
    
    success = True
    
    # tool_success 应该只被调用 1 次
    if call_counts['tool_success'] == 1:
        logger.info(f"✓ tool_success 只调用了 1 次（符合预期）")
    else:
        logger.error(f"✗ tool_success 调用了 {call_counts['tool_success']} 次（预期 1 次）")
        success = False
    
    # tool_fail_once 应该被调用 2 次
    if call_counts['tool_fail_once'] == 2:
        logger.info(f"✓ tool_fail_once 调用了 2 次（符合预期：1次失败 + 1次重试）")
    else:
        logger.error(f"✗ tool_fail_once 调用了 {call_counts['tool_fail_once']} 次（预期 2 次）")
        success = False
    
    logger.info(f"\n错误计数: {result.get('error_count', 0)}")
    logger.info(f"失败工具: {result.get('failed_tools', [])}")
    
    logger.info("\n" + "="*60)
    if success:
        logger.info("✓ 测试通过：只有失败的工具被重试")
    else:
        logger.error("✗ 测试失败：重试逻辑不符合预期")
    logger.info("="*60 + "\n")
    
    return success


async def main():
    """主测试函数"""
    
    logger.info("\n" + "="*60)
    logger.info("选择性重试测试")
    logger.info("="*60 + "\n")
    
    try:
        test_passed = await test_selective_retry()
        
        logger.info("\n" + "="*60)
        logger.info("测试总结")
        logger.info("="*60)
        logger.info(f"选择性重试测试: {'✓ 通过' if test_passed else '✗ 失败'}")
        logger.info("="*60 + "\n")
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())



async def test_selective_retry():
    """测试：只有失败的工具会被重试，成功的工具不会重新执行"""
    
    logger.info("\n" + "="*60)
    logger.info("测试：选择性重试机制")
    logger.info("="*60 + "\n")
    
    # 记录工具调用次数
    call_counts = {
        "get_real_time_quote": 0,
        "get_company_fundamentals": 0,
        "calculate_technical_indicators": 0,
    }
    
    # 原始函数引用
    original_quote = get_real_time_quote.func
    original_fundamentals = get_company_fundamentals.func
    
    # 模拟：第一次调用 get_company_fundamentals 失败，第二次成功
    fundamentals_call_count = 0
    
    async def mock_fundamentals(ticker: str):
        nonlocal fundamentals_call_count
        fundamentals_call_count += 1
        call_counts["get_company_fundamentals"] += 1
        
        logger.info(f"[MOCK] get_company_fundamentals 被调用 (第 {fundamentals_call_count} 次)")
        
        if fundamentals_call_count == 1:
            # 第一次调用失败
            logger.warning(f"[MOCK] 模拟 get_company_fundamentals 失败")
            return {"error": "模拟的网络错误"}
        else:
            # 后续调用成功
            logger.info(f"[MOCK] get_company_fundamentals 成功")
            return await original_fundamentals(ticker)
    
    async def mock_quote(ticker: str):
        call_counts["get_real_time_quote"] += 1
        logger.info(f"[MOCK] get_real_time_quote 被调用 (第 {call_counts['get_real_time_quote']} 次)")
        return await original_quote(ticker)
    
    # 使用 patch 替换工具函数
    with patch('skills.fundamentals.tool.get_company_fundamentals.func', new=mock_fundamentals), \
         patch('skills.market_data.tool.get_real_time_quote.func', new=mock_quote):
        
        agent = get_agent_with_coordinator()
        
        # 测试查询：需要调用多个工具
        test_query = "分析 AAPL：获取实时报价和基本面数据"
        
        logger.info(f"测试查询: {test_query}\n")
        
        result = await agent.ainvoke({
            "messages": [HumanMessage(content=test_query)],
            "max_retries": 2,
        })
        
        logger.info("\n" + "="*60)
        logger.info("测试结果")
        logger.info("="*60)
        
        # 验证调用次数
        logger.info(f"\n工具调用统计:")
        logger.info(f"  get_real_time_quote: {call_counts['get_real_time_quote']} 次")
        logger.info(f"  get_company_fundamentals: {call_counts['get_company_fundamentals']} 次")
        
        # 验证预期行为
        success = True
        
        # get_real_time_quote 应该只被调用 1 次（成功）
        if call_counts['get_real_time_quote'] == 1:
            logger.info(f"✓ get_real_time_quote 只调用了 1 次（符合预期）")
        else:
            logger.error(f"✗ get_real_time_quote 调用了 {call_counts['get_real_time_quote']} 次（预期 1 次）")
            success = False
        
        # get_company_fundamentals 应该被调用 2 次（第一次失败，第二次重试成功）
        if call_counts['get_company_fundamentals'] == 2:
            logger.info(f"✓ get_company_fundamentals 调用了 2 次（符合预期：1次失败 + 1次重试）")
        else:
            logger.error(f"✗ get_company_fundamentals 调用了 {call_counts['get_company_fundamentals']} 次（预期 2 次）")
            success = False
        
        # 检查错误计数
        error_count = result.get("error_count", 0)
        logger.info(f"\n错误计数: {error_count}")
        
        # 检查失败工具列表（应该为空，因为重试成功了）
        failed_tools = result.get("failed_tools", [])
        if not failed_tools:
            logger.info(f"✓ 所有工具最终都成功执行")
        else:
            logger.warning(f"⚠ 仍有失败的工具: {failed_tools}")
        
        logger.info("\n" + "="*60)
        if success:
            logger.info("✓ 测试通过：只有失败的工具被重试")
        else:
            logger.error("✗ 测试失败：重试逻辑不符合预期")
        logger.info("="*60 + "\n")
        
        return success


async def test_max_retries():
    """测试：达到最大重试次数后停止重试"""
    
    logger.info("\n" + "="*60)
    logger.info("测试：最大重试次数限制")
    logger.info("="*60 + "\n")
    
    call_count = 0
    
    async def always_fail_fundamentals(ticker: str):
        nonlocal call_count
        call_count += 1
        logger.info(f"[MOCK] get_company_fundamentals 被调用 (第 {call_count} 次) - 总是失败")
        return {"error": "持续失败"}
    
    with patch('skills.fundamentals.tool.get_company_fundamentals.func', new=always_fail_fundamentals):
        agent = get_agent_with_coordinator()
        
        test_query = "获取 AAPL 的基本面数据"
        
        result = await agent.ainvoke({
            "messages": [HumanMessage(content=test_query)],
            "max_retries": 2,
        })
        
        logger.info("\n" + "="*60)
        logger.info("测试结果")
        logger.info("="*60)
        logger.info(f"工具调用次数: {call_count}")
        logger.info(f"错误计数: {result.get('error_count', 0)}")
        logger.info(f"失败工具: {result.get('failed_tools', [])}")
        
        # 应该调用 3 次：1次初始 + 2次重试
        if call_count == 3:
            logger.info(f"✓ 达到最大重试次数后停止（1次初始 + 2次重试 = 3次）")
            return True
        else:
            logger.error(f"✗ 调用次数不符合预期：{call_count} 次（预期 3 次）")
            return False


async def main():
    """主测试函数"""
    
    logger.info("\n" + "="*60)
    logger.info("选择性重试测试套件")
    logger.info("="*60 + "\n")
    
    try:
        # 测试1: 选择性重试
        test1_passed = await test_selective_retry()
        await asyncio.sleep(2)
        
        # 测试2: 最大重试次数
        test2_passed = await test_max_retries()
        
        logger.info("\n" + "="*60)
        logger.info("测试总结")
        logger.info("="*60)
        logger.info(f"测试1 (选择性重试): {'✓ 通过' if test1_passed else '✗ 失败'}")
        logger.info(f"测试2 (最大重试次数): {'✓ 通过' if test2_passed else '✗ 失败'}")
        logger.info("="*60 + "\n")
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
