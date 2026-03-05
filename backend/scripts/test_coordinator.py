"""
测试协调器模式 vs 标准模式

对比：
1. 标准 ReAct Agent（可能产生幻觉）
2. 带协调器的 Agent（强制工具使用）
"""

import asyncio
from langchain_core.messages import HumanMessage

from core.agent.graph import get_agent
from core.agent.graph_with_coordinator import get_agent_with_coordinator


# 测试用例：容易产生幻觉的问题
TEST_CASES = [
    "阿里巴巴现在股价多少？",
    "特斯拉的 RSI 指标是多少？",
    "什么是市盈率？",
    "苹果公司最近有什么新闻？",
    "比特币今天涨了多少？",
]


async def test_standard_agent(question: str):
    """测试标准 Agent"""
    print(f"\n{'='*60}")
    print(f"📝 问题: {question}")
    print(f"{'='*60}")
    print("\n🔵 标准模式（可能产生幻觉）:")
    print("-" * 60)
    
    agent = get_agent()
    state = {"messages": [HumanMessage(content=question)]}
    
    result = await agent.ainvoke(state)
    
    # 分析是否使用了工具
    messages = result["messages"]
    tool_calls = [
        m for m in messages 
        if hasattr(m, "tool_calls") and m.tool_calls
    ]
    
    final_answer = messages[-1].content if messages else "无回答"
    
    print(f"\n工具调用次数: {len(tool_calls)}")
    if tool_calls:
        for msg in tool_calls:
            for tc in msg.tool_calls:
                print(f"  - {tc['name']}({tc['args']})")
    else:
        print("  ⚠️ 没有调用任何工具！")
    
    print(f"\n最终回答:\n{final_answer}")


async def test_coordinator_agent(question: str):
    """测试带协调器的 Agent"""
    print(f"\n🟢 协调器模式（强制工具使用）:")
    print("-" * 60)
    
    agent = get_agent_with_coordinator()
    state = {"messages": [HumanMessage(content=question)]}
    
    result = await agent.ainvoke(state)
    
    # 分析协调器的规划
    tool_plan = result.get("tool_plan", [])
    reasoning = result.get("coordination_reasoning", "")
    
    print(f"\n协调器分析: {reasoning}")
    if tool_plan:
        print(f"\n工具计划:")
        for plan in tool_plan:
            print(f"  - {plan.get('tool')} → {plan.get('purpose')}")
    
    # 分析实际工具调用
    messages = result["messages"]
    tool_calls = [
        m for m in messages 
        if hasattr(m, "tool_calls") and m.tool_calls
    ]
    
    print(f"\n实际工具调用次数: {len(tool_calls)}")
    if tool_calls:
        for msg in tool_calls:
            for tc in msg.tool_calls:
                print(f"  - {tc['name']}({tc['args']})")
    
    # 检查验证结果
    validation_failed = result.get("validation_failed", False)
    if validation_failed:
        print("\n⚠️ 验证失败：Agent 没有按要求使用工具")
    
    final_answer = messages[-1].content if messages else "无回答"
    print(f"\n最终回答:\n{final_answer}")


async def main():
    """运行对比测试"""
    print("\n" + "="*60)
    print("协调器模式 vs 标准模式 对比测试")
    print("="*60)
    
    for question in TEST_CASES:
        try:
            await test_standard_agent(question)
            await test_coordinator_agent(question)
            
            print("\n" + "="*60)
            input("按 Enter 继续下一个测试...")
            
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
