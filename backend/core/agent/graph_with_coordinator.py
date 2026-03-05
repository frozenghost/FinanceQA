"""
带协调器的 LangGraph Agent - 强制工具使用，减少幻觉

架构：
1. coordinator: 分析问题，规划工具调用
2. router: 决定是否需要工具
3. enforcer: 强制要求使用工具（显示进度）
4. agent: 执行工具调用和生成答案
5. tools: 执行工具（自动跟踪）
6. validator: 验证是否按计划执行了所有工具
"""

from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, SystemMessage

from core.agent.state import AgentState
from core.agent.coordinator import (
    coordinate_tools,
    should_use_tools,
    enforce_tool_usage,
    validate_tool_usage,
)
from prompts.loader import load_system_prompt
from services.llm_client import LLMClient
from skills import ALL_TOOLS


def agent_node(state: AgentState) -> dict:
    """Agent 节点：调用 LLM 进行推理和工具调用"""
    llm = LLMClient().get_langchain_model(role="market_analyst")
    
    # 绑定工具
    llm_with_tools = llm.bind_tools(ALL_TOOLS)
    
    # 获取系统提示（只在第一次调用时添加）
    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) and "你是一个专业的金融分析助手" in m.content for m in messages):
        # 使用严格模式的 prompt
        system_prompt = load_system_prompt(strict=True)
        messages = [SystemMessage(content=system_prompt)] + messages
    
    # 调用 LLM
    response = llm_with_tools.invoke(messages)
    
    return {"messages": [response]}


def tools_with_tracking(state: AgentState) -> dict:
    """工具执行节点：执行工具并自动跟踪"""
    # 执行工具
    tool_node = ToolNode(ALL_TOOLS)
    result = tool_node.invoke(state)
    
    # 跟踪已执行的工具
    messages = result.get("messages", state["messages"])
    executed_tools = state.get("executed_tools", [])
    
    # 查找最近的工具调用
    for msg in reversed(messages[-10:]):
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                tool_name = tool_call.get("name", "")
                if tool_name and tool_name not in executed_tools:
                    executed_tools.append(tool_name)
    
    result["executed_tools"] = executed_tools
    return result


def should_continue(state: AgentState) -> Literal["tools", "validate", "end"]:
    """
    决定下一步：
    - 如果有工具调用 → 执行工具
    - 如果没有工具调用但需要验证 → 验证
    - 否则 → 结束
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    # 如果有工具调用，执行工具
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    
    # 如果协调器要求使用工具，需要验证
    needs_tools = state.get("needs_tools", False)
    tool_plan = state.get("tool_plan", [])
    
    if needs_tools or tool_plan:
        return "validate"
    
    return "end"


def check_validation(state: AgentState) -> Literal["enforcer", "end"]:
    """
    检查验证结果：
    - 如果验证失败 → 返回 enforcer 重新强制（显示进度）
    - 否则 → 结束
    """
    validation_failed = state.get("validation_failed", False)
    
    if validation_failed:
        return "enforcer"
    return "end"


def build_agent_with_coordinator():
    """构建带协调器的 Agent"""
    
    # 创建状态图
    workflow = StateGraph(AgentState)
    
    # 添加节点
    workflow.add_node("coordinator", coordinate_tools)          # 协调器：规划工具
    workflow.add_node("enforcer", enforce_tool_usage)           # 强制器：添加强制指令（显示进度）
    workflow.add_node("agent", agent_node)                      # Agent：LLM 推理
    workflow.add_node("tools", tools_with_tracking)             # 工具执行（自动跟踪）
    workflow.add_node("validator", validate_tool_usage)         # 验证器：检查工具使用
    
    # 设置入口
    workflow.set_entry_point("coordinator")
    
    # 协调器 → 路由（是否需要工具）
    workflow.add_conditional_edges(
        "coordinator",
        should_use_tools,
        {
            "use_tools": "enforcer",      # 需要工具 → 强制器
            "direct_answer": "agent",     # 不需要工具 → 直接回答
        }
    )
    
    # 强制器 → Agent
    workflow.add_edge("enforcer", "agent")
    
    # Agent → 条件路由
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",         # 有工具调用 → 执行工具（自动跟踪）
            "validate": "validator",  # 需要验证 → 验证器
            "end": END,              # 结束
        }
    )
    
    # 工具执行后 → 返回 Agent（继续推理）
    workflow.add_edge("tools", "agent")
    
    # 验证器 → 条件路由
    workflow.add_conditional_edges(
        "validator",
        check_validation,
        {
            "enforcer": "enforcer",  # 验证失败 → 重新强制（显示进度）
            "end": END,              # 验证通过 → 结束
        }
    )
    
    return workflow.compile()


# 懒加载单例
_agent_with_coordinator = None


def get_agent_with_coordinator():
    """获取或创建带协调器的 Agent 实例"""
    global _agent_with_coordinator
    if _agent_with_coordinator is None:
        _agent_with_coordinator = build_agent_with_coordinator()
    return _agent_with_coordinator
