"""测试协调器的工具调用一致性"""

import asyncio
from langchain_core.messages import HumanMessage
from core.agent.graph import get_agent


async def test_coordinator_consistency():
    """测试协调器规划与实际执行的一致性"""
    
    test_cases = [
        {
            "name": "单工具调用",
            "query": "AAPL 现在多少钱？",
            "expected_tools": ["get_real_time_quote"],
        },
        {
            "name": "多工具调用 - 基本面+技术面",
            "query": "分析 TSLA 的基本面和技术面",
            "expected_tools": ["get_company_fundamentals", "calculate_technical_indicators"],
        },
        {
            "name": "复合查询 - 价格+新闻+技术指标",
            "query": "BABA 最近表现如何？包括价格、新闻和技术指标",
            "expected_tools": ["get_real_time_quote", "get_financial_news", "calculate_technical_indicators"],
        },
    ]
    
    agent = get_agent()
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'='*80}")
        print(f"测试 {i}: {test_case['name']}")
        print(f"问题: {test_case['query']}")
        print(f"预期工具: {', '.join(test_case['expected_tools'])}")
        print(f"{'='*80}\n")
        
        # 执行查询
        state = {"messages": [HumanMessage(content=test_case["query"])]}
        
        try:
            result = await agent.ainvoke(state)
            
            # 提取执行的工具
            executed_tools = result.get("executed_tools", [])
            tool_plan = result.get("tool_plan", [])
            planned_tools = [t["tool"] for t in tool_plan]
            
            print(f"📋 协调器计划: {', '.join(planned_tools) if planned_tools else '无'}")
            print(f"✓ 实际执行: {', '.join(executed_tools) if executed_tools else '无'}")
            
            # 检查一致性
            if set(planned_tools) == set(executed_tools):
                print(f"✅ 一致性检查: 通过")
            else:
                missing = set(planned_tools) - set(executed_tools)
                extra = set(executed_tools) - set(planned_tools)
                print(f"❌ 一致性检查: 失败")
                if missing:
                    print(f"   缺失工具: {', '.join(missing)}")
                if extra:
                    print(f"   额外工具: {', '.join(extra)}")
            
            # 显示最终答案
            final_message = result["messages"][-1]
            if hasattr(final_message, "content"):
                print(f"\n💬 最终答案:\n{final_message.content[:200]}...")
            
        except Exception as e:
            print(f"❌ 执行失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_coordinator_consistency())
