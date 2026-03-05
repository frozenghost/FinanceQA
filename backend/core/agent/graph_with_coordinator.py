"""
带协调器的 LangGraph Agent - 强制工具使用，减少幻觉

架构：
1. coordinator: 分析问题，规划工具调用
2. enforcer: 强制要求使用工具
3. agent: 执行工具调用和生成答案
4. tools: 并行执行工具（自动）
"""

import logging
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, SystemMessage

from core.agent.state import AgentState
from core.agent.coordinator import (
    coordinate_tools,
    should_use_tools,
    enforce_tool_usage,
)
from prompts.loader import load_system_prompt
from services.llm_client import LLMClient
from skills import ALL_TOOLS

logger = logging.getLogger(__name__)


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
    
    logger.info("[agent_node] 调用 LLM 进行推理")
    
    # 调用 LLM
    response = llm_with_tools.invoke(messages)
    
    # 检查是否有工具调用
    if isinstance(response, AIMessage) and response.tool_calls:
        tool_names = [tc.get("name", "unknown") for tc in response.tool_calls]
        logger.info(f"[agent_node] LLM 请求调用 {len(tool_names)} 个工具: {', '.join(tool_names)}")
    else:
        logger.info("[agent_node] LLM 生成最终答案（无工具调用）")
    
    return {"messages": [response]}


def track_executed_tools(state: AgentState) -> dict:
    """跟踪已执行的工具"""
    messages = state["messages"]
    executed_tools = []
    
    # 遍历所有消息，收集已执行的工具
    for msg in messages:
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                tool_name = tool_call.get("name", "")
                if tool_name and tool_name not in executed_tools:
                    executed_tools.append(tool_name)
    
    # 对比计划和实际执行
    tool_plan = state.get("tool_plan", [])
    if tool_plan:
        planned_tools = [t["tool"] for t in tool_plan]
        logger.info(f"[tracker] 工具执行统计:")
        logger.info(f"  计划: {len(planned_tools)} 个 - {', '.join(planned_tools)}")
        logger.info(f"  实际: {len(executed_tools)} 个 - {', '.join(executed_tools)}")
        
        missing = set(planned_tools) - set(executed_tools)
        extra = set(executed_tools) - set(planned_tools)
        
        if missing:
            logger.warning(f"  缺失: {', '.join(missing)}")
        if extra:
            logger.info(f"  额外: {', '.join(extra)}")
        if not missing and not extra:
            logger.info(f"  ✓ 完全一致")
    
    return {"executed_tools": executed_tools}


def should_continue(state: AgentState) -> Literal["tools", "end"]:
    """
    决定下一步：
    - 如果有工具调用 → 执行工具
    - 否则 → 结束
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    # 如果有工具调用，执行工具
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    
    return "end"


def build_agent_with_coordinator():
    """构建带协调器的 Agent
    
    注意：ToolNode 默认支持并行执行！
    当 LLM 返回多个 tool_calls 时，它们会并发执行，然后一起返回结果。
    """
    
    # 创建状态图
    workflow = StateGraph(AgentState)
    
    # 添加节点
    workflow.add_node("coordinator", coordinate_tools)          # 协调器：规划工具
    workflow.add_node("enforcer", enforce_tool_usage)           # 强制器：添加强制指令
    workflow.add_node("agent", agent_node)                      # Agent：LLM 推理
    workflow.add_node("tools", ToolNode(ALL_TOOLS))             # 工具执行（自动并行）
    workflow.add_node("tracker", track_executed_tools)          # 跟踪器：统计执行的工具
    
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
            "tools": "tools",         # 有工具调用 → 并行执行工具
            "end": "tracker",         # 结束 → 跟踪器（统计）
        }
    )
    
    # 工具执行后 → 返回 Agent（继续推理）
    workflow.add_edge("tools", "agent")
    
    # 跟踪器 → 结束
    workflow.add_edge("tracker", END)
    
    return workflow.compile()


# 懒加载单例
_agent_with_coordinator = None


def get_agent_with_coordinator():
    """获取或创建带协调器的 Agent 实例"""
    global _agent_with_coordinator
    if _agent_with_coordinator is None:
        _agent_with_coordinator = build_agent_with_coordinator()
    return _agent_with_coordinator
