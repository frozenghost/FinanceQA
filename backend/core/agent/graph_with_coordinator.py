"""
带协调器的 LangGraph Agent - 强制工具使用，减少幻觉

架构：
1. coordinator: 分析问题，规划工具调用
2. enforcer: 强制要求使用工具
3. agent: 执行工具调用和生成答案
4. tools: 并行执行工具（异步+错误处理）
5. error_handler: 处理工具执行失败
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
    """Agent 节点：调用 LLM 进行推理和工具调用"""
    llm = LLMClient().get_langchain_model(role="market_analyst")
    
    # 绑定工具，启用并行工具调用
    llm_with_tools = llm.bind_tools(ALL_TOOLS, parallel_tool_calls=True)
    
    # 获取系统提示（只在第一次调用时添加）
    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) and "你是一个专业的金融分析助手" in m.content for m in messages):
        # 使用严格模式的 prompt
        system_prompt = load_system_prompt(strict=True)
        messages = [SystemMessage(content=system_prompt)] + messages
    
    logger.info("[agent_node] 调用 LLM 进行推理")
    
    # 异步调用 LLM
    response = await llm_with_tools.ainvoke(messages)
    
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
    seen = set()
    
    # 遍历所有消息，收集已执行的工具（去重，保留参数）
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
    
    # 对比计划和实际执行
    tool_plan = state.get("tool_plan", [])
    if tool_plan:
        planned_tools = [t["tool"] for t in tool_plan]
        executed_names = [t["tool"] for t in executed_tools]
        logger.info("[tracker] 工具执行统计:")
        logger.info(f"  计划: {len(planned_tools)} 个 - {', '.join(planned_tools)}")
        logger.info(f"  实际: {len(executed_names)} 个 - {', '.join(executed_names)}")

        missing = set(planned_tools) - set(executed_names)
        extra = set(executed_names) - set(planned_tools)
        
        if missing:
            logger.warning(f"  缺失: {', '.join(missing)}")
        if extra:
            logger.info(f"  额外: {', '.join(extra)}")
        if not missing and not extra:
            logger.info("  ✓ 完全一致")

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


async def enhanced_tool_node(state: AgentState) -> dict:
    """增强的工具执行节点：带超时、错误处理和性能监控"""
    messages = state["messages"]
    last_message = messages[-1]
    
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return state
    
    tool_calls = last_message.tool_calls
    logger.info(f"[enhanced_tool_node] 开始并行执行 {len(tool_calls)} 个工具")
    
    start_time = time.time()
    tool_messages = []
    
    async def execute_single_tool(tool_call):
        """执行单个工具，带超时和错误处理"""
        tool_name = tool_call.get("name", "unknown")
        tool_id = tool_call.get("id", "")
        
        try:
            # 查找工具
            tool = next((t for t in ALL_TOOLS if t.name == tool_name), None)
            if not tool:
                return ToolMessage(
                    content=f"错误：工具 '{tool_name}' 不存在",
                    tool_call_id=tool_id
                )
            
            # 执行工具，设置30秒超时
            logger.info(f"[tool:{tool_name}] 开始执行")
            tool_start = time.time()
            
            result = await asyncio.wait_for(
                tool.ainvoke(tool_call.get("args", {})),
                timeout=30.0
            )
            
            tool_elapsed = time.time() - tool_start
            logger.info(f"[tool:{tool_name}] 完成，耗时 {tool_elapsed:.2f}s")
            
            return ToolMessage(
                content=str(result),
                tool_call_id=tool_id
            )
            
        except asyncio.TimeoutError:
            logger.error(f"[tool:{tool_name}] 执行超时（>30s）")
            return ToolMessage(
                content=f"错误：工具 '{tool_name}' 执行超时",
                tool_call_id=tool_id
            )
        except Exception as e:
            logger.error(f"[tool:{tool_name}] 执行失败: {e}", exc_info=True)
            return ToolMessage(
                content=f"错误：工具 '{tool_name}' 执行失败 - {str(e)}",
                tool_call_id=tool_id
            )
    
    # 并行执行所有工具
    tool_messages = await asyncio.gather(
        *[execute_single_tool(tc) for tc in tool_calls],
        return_exceptions=False
    )
    
    total_elapsed = time.time() - start_time
    logger.info(f"[enhanced_tool_node] 所有工具执行完成，总耗时 {total_elapsed:.2f}s")
    
    return {"messages": list(tool_messages)}


def error_handler_node(state: AgentState) -> dict:
    """错误处理节点：分析工具执行失败并记录失败的工具"""
    messages = state["messages"]
    error_count = state.get("error_count", 0)
    failed_tools = state.get("failed_tools", [])
    
    # 检查最近的工具消息是否有错误，并记录失败的工具名称
    tool_errors = []
    new_failed_tools = []
    
    # 找到最后一个 AIMessage 的 tool_calls
    last_ai_message = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            last_ai_message = msg
            break
    
    if last_ai_message:
        # 检查每个工具调用的结果
        for tool_call in last_ai_message.tool_calls:
            tool_name = tool_call.get("name", "")
            tool_id = tool_call.get("id", "")
            
            # 查找对应的 ToolMessage
            tool_msg = next(
                (m for m in reversed(messages) 
                 if isinstance(m, ToolMessage) and m.tool_call_id == tool_id),
                None
            )
            
            if tool_msg and "错误" in tool_msg.content:
                tool_errors.append(tool_msg.content)
                if tool_name not in failed_tools:
                    new_failed_tools.append(tool_name)
    
    if tool_errors:
        logger.warning(f"[error_handler] 检测到 {len(tool_errors)} 个工具错误")
        for err in tool_errors:
            logger.warning(f"  - {err}")
    
    return {
        "error_count": error_count + len(tool_errors),
        "last_error": tool_errors[0] if tool_errors else None,
        "failed_tools": failed_tools + new_failed_tools,
    }


async def retry_failed_tools_node(state: AgentState) -> dict:
    """重试失败的工具节点：只重新执行失败的工具"""
    messages = state["messages"]
    failed_tools = state.get("failed_tools", [])
    
    if not failed_tools:
        return state
    
    logger.info(f"[retry_failed_tools] 重试 {len(failed_tools)} 个失败的工具: {', '.join(failed_tools)}")
    
    # 找到最后一个 AIMessage 的 tool_calls
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
        if tc.get("name", "") in failed_tools
    ]
    
    if not failed_tool_calls:
        return state
    
    logger.info(f"[retry_failed_tools] 开始重试 {len(failed_tool_calls)} 个工具调用")
    start_time = time.time()
    
    async def execute_single_tool(tool_call):
        """执行单个工具，带超时和错误处理"""
        tool_name = tool_call.get("name", "unknown")
        tool_id = tool_call.get("id", "")
        
        try:
            # 查找工具
            tool = next((t for t in ALL_TOOLS if t.name == tool_name), None)
            if not tool:
                return ToolMessage(
                    content=f"错误：工具 '{tool_name}' 不存在",
                    tool_call_id=tool_id
                )
            
            # 执行工具，设置30秒超时
            logger.info(f"[tool:{tool_name}] 重试执行")
            tool_start = time.time()
            
            result = await asyncio.wait_for(
                tool.ainvoke(tool_call.get("args", {})),
                timeout=30.0
            )
            
            tool_elapsed = time.time() - tool_start
            logger.info(f"[tool:{tool_name}] 重试完成，耗时 {tool_elapsed:.2f}s")
            
            return ToolMessage(
                content=str(result),
                tool_call_id=tool_id
            )
            
        except asyncio.TimeoutError:
            logger.error(f"[tool:{tool_name}] 重试超时（>30s）")
            return ToolMessage(
                content=f"错误：工具 '{tool_name}' 执行超时",
                tool_call_id=tool_id
            )
        except Exception as e:
            logger.error(f"[tool:{tool_name}] 重试失败: {e}", exc_info=True)
            return ToolMessage(
                content=f"错误：工具 '{tool_name}' 执行失败 - {str(e)}",
                tool_call_id=tool_id
            )
    
    # 并行重试所有失败的工具
    retry_messages = await asyncio.gather(
        *[execute_single_tool(tc) for tc in failed_tool_calls],
        return_exceptions=False
    )
    
    total_elapsed = time.time() - start_time
    logger.info(f"[retry_failed_tools] 重试完成，总耗时 {total_elapsed:.2f}s")
    
    # 替换原来失败的 ToolMessage
    updated_messages = []
    retry_msg_dict = {msg.tool_call_id: msg for msg in retry_messages}
    
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.tool_call_id in retry_msg_dict:
            # 替换为重试后的消息
            updated_messages.append(retry_msg_dict[msg.tool_call_id])
        else:
            updated_messages.append(msg)
    
    return {
        "messages": updated_messages,
        "failed_tools": [],  # 清空失败工具列表
    }


def should_retry(state: AgentState) -> Literal["retry", "continue"]:
    """决定是否重试失败的工具"""
    error_count = state.get("error_count", 0)
    max_retries = state.get("max_retries", 2)
    failed_tools = state.get("failed_tools", [])
    
    # 只有在有失败工具且未超过重试次数时才重试
    if failed_tools and error_count < max_retries:
        logger.info(f"[should_retry] 将重试失败的工具: {', '.join(failed_tools)} (尝试 {error_count + 1}/{max_retries})")
        return "retry"
    
    if failed_tools and error_count >= max_retries:
        logger.warning(f"[should_retry] 已达到最大重试次数，放弃重试: {', '.join(failed_tools)}")
    
    return "continue"


def build_agent_with_coordinator():
    """构建带协调器的 Agent
    
    优化点：
    1. 异步并行工具执行（asyncio.gather）
    2. 超时控制（30秒/工具）
    3. 错误处理和重试机制
    4. 性能监控和日志
    """
    
    # 创建状态图
    workflow = StateGraph(AgentState)
    
    # 添加节点
    workflow.add_node("coordinator", coordinator_chain)           # 协调器：规划工具（LCEL 便于流式）
    workflow.add_node("enforcer", enforce_tool_usage)           # 强制器：添加强制指令
    workflow.add_node("agent", agent_node)                      # Agent：LLM 推理（异步）
    workflow.add_node("tools", enhanced_tool_node)              # 工具执行（增强版）
    workflow.add_node("error_handler", error_handler_node)      # 错误处理
    workflow.add_node("retry_tools", retry_failed_tools_node)   # 重试失败的工具
    workflow.add_node("tracker", track_executed_tools)          # 跟踪器：统计执行的工具
    workflow.add_node("validator", validate_tool_execution)     # 验证器：对比规划与实际执行
    
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
    
    # 工具执行后 → 错误处理
    workflow.add_edge("tools", "error_handler")
    
    # 错误处理 → 条件路由（重试或继续）
    workflow.add_conditional_edges(
        "error_handler",
        should_retry,
        {
            "retry": "retry_tools",   # 重试 → 只重试失败的工具
            "continue": "agent",      # 继续 → 返回 Agent（带错误信息）
        }
    )
    
    # 重试工具后 → 返回 Agent
    workflow.add_edge("retry_tools", "agent")
    
    # 跟踪器 → 验证器 → 结束
    workflow.add_edge("tracker", "validator")
    workflow.add_edge("validator", END)
    
    return workflow.compile()


# 懒加载单例
_agent_with_coordinator = None


def get_agent_with_coordinator():
    """获取或创建带协调器的 Agent 实例"""
    global _agent_with_coordinator
    if _agent_with_coordinator is None:
        _agent_with_coordinator = build_agent_with_coordinator()
    return _agent_with_coordinator
