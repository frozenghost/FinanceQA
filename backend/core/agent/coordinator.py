"""
协调器节点 - 强制工具使用，减少模型幻觉

核心思想：
1. 在模型回答前，先由协调器分析问题并规划工具调用
2. 强制要求必须使用工具获取数据，禁止直接回答
3. 最后统计验证工具执行情况
"""

import json
import logging
from pathlib import Path
from typing import Literal

from datetime import datetime
from zoneinfo import ZoneInfo
import json_repair
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def get_time_context() -> str:
    """生成当前时间上下文信息"""
    utc_now = datetime.now(ZoneInfo("UTC"))
    
    timezones = {
        "UTC": "UTC",
        "US/Eastern": "America/New_York",
        "Asia/Shanghai": "Asia/Shanghai",
        "Asia/Hong_Kong": "Asia/Hong_Kong",
    }
    
    time_info = "## 当前时间\n"
    for display_name, tz_name in timezones.items():
        try:
            local_time = utc_now.astimezone(ZoneInfo(tz_name))
            time_info += f"- {display_name}: {local_time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        except Exception:
            time_info += f"- {display_name}: {utc_now.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
    
    time_info += f"\n**重要**：用户询问\"最新\"、\"最近\"时，应基于上述实际时间，而非模型训练时间。\n"
    return time_info


def load_coordinator_prompt() -> str:
    """加载协调器提示词模板"""
    # 项目中协调器提示词统一放在 backend/prompts/coordinator.md
    # 这里从 backend 目录向上两级，再进入 prompts 目录
    prompt_path = Path(__file__).parents[2] / "prompts" / "coordinator.md"
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to load coordinator prompt: {e}")
        # 返回一个基本的后备提示词
        return """你是一个工具调用协调器，负责分析用户问题并规划工具调用策略。
请分析用户问题，判断需要调用哪些工具，并输出 JSON 格式的工具调用计划。"""



def _state_to_messages(state: dict) -> list:
    """Build coordination messages from graph state (for LCEL chain)."""
    messages = state["messages"]
    last_user_message = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
        "",
    )
    time_context = get_time_context()
    coordinator_prompt = load_coordinator_prompt()
    full_prompt = time_context + "\n\n" + coordinator_prompt
    return [
        SystemMessage(content=full_prompt),
        HumanMessage(content=f"用户问题：{last_user_message}\n\n请规划工具调用策略。"),
    ]


def _parse_coordinator_output(aimessage: AIMessage) -> dict:
    """Parse coordinator LLM output into state update."""
    content = aimessage.content or ""
    
    # 保存原始输出用于流式传输（包含 Markdown 部分）
    raw_output = content
    
    try:
        # 提取 JSON 部分（在最后的代码块中）
        json_content = content
        if "```json" in content:
            # 找到最后一个 json 代码块
            parts = content.split("```json")
            if len(parts) > 1:
                json_content = parts[-1].split("```")[0].strip()
        elif "```" in content:
            # 找到最后一个代码块
            parts = content.split("```")
            if len(parts) >= 3:
                json_content = parts[-2].strip()

        # 使用 json_repair.loads 替代 json.loads，自动修复并解析
        plan = json_repair.loads(json_content)
        tool_plan = plan.get("tool_plan", [])
        logger.info(f"协调器规划: {len(tool_plan)} 个工具")
        
        # 基于结构化 plan 构造稳定的 Markdown（不直接透传原始 JSON）
        reasoning_text = plan.get("reasoning", "").strip()
        tool_plan_md_lines = []
        for t in tool_plan:
            name = t.get("tool", "")
            params = t.get("params", {}) or {}
            purpose = t.get("purpose", "") or ""
            params_str = ", ".join(f"{k}={v}" for k, v in params.items())
            tool_line = f"- **{name}**({params_str})"
            if purpose:
                tool_line += f" - {purpose}"
            tool_plan_md_lines.append(tool_line)

        markdown_parts = ["## 分析"]
        if reasoning_text:
            markdown_parts.append(reasoning_text)
        markdown_parts.append("")  # blank line
        if tool_plan_md_lines:
            markdown_parts.append("## 工具调用计划")
            markdown_parts.extend(tool_plan_md_lines)
        markdown_content = "\n".join(markdown_parts).strip()
        
        return {
            "tool_plan": tool_plan,
            "needs_tools": plan.get("needs_tools", True),
            "coordination_reasoning": plan.get("reasoning", ""),
            "coordinator_raw_output": raw_output,  # 完整输出（Markdown + JSON）
            "coordinator_markdown": markdown_content,  # 仅 Markdown 部分
        }
    except Exception as e:
        logger.error(f"协调器输出解析失败: {e}")
        return {
            "tool_plan": [],
            "needs_tools": True,
            "coordination_reasoning": "协调器解析失败，将由 agent 自行判断",
            "coordinator_raw_output": raw_output,
            "coordinator_markdown": raw_output,  # 解析失败时使用原始输出
        }


def _get_coordinator_chain():
    """LCEL chain so astream_events emits on_chat_model_stream for coordinator LLM."""
    llm = LLMClient().get_langchain_model(role="coordinator")
    return (
        RunnableLambda(_state_to_messages)
        | llm
        | RunnableLambda(_parse_coordinator_output)
    )


# Runnable used as coordinator node; streaming is visible in astream_events
coordinator_chain = _get_coordinator_chain()


async def coordinate_tools(state: dict) -> dict:
    """Wrapper for backward compatibility; prefer using coordinator_chain as node."""
    return await coordinator_chain.ainvoke(state)


def should_use_tools(state: dict) -> Literal["use_tools", "direct_answer"]:
    """
    路由函数：决定是否需要使用工具
    """
    needs_tools = state.get("needs_tools", True)
    tool_plan = state.get("tool_plan", [])
    
    # 如果协调器明确表示需要工具，或者有工具计划，则使用工具
    if needs_tools or tool_plan:
        return "use_tools"
    else:
        return "direct_answer"


def enforce_tool_usage(state: dict) -> dict:
    """
    强制工具使用节点：基于协调器的计划，强制要求 agent 使用工具
    """
    tool_plan = state.get("tool_plan", [])
    reasoning = state.get("coordination_reasoning", "")
    
    if not tool_plan:
        # 没有具体计划，但仍需要工具，给出通用指导
        enforcement_msg = """
⚠️ 协调器判断：此问题需要使用工具获取数据

请根据问题类型选择合适的工具：
- 股票报价 → get_real_time_quote
- 历史价格 → get_historical_prices
- 基本面分析 → get_company_fundamentals
- 财报数据 → get_earnings_history
- 技术指标 → calculate_technical_indicators  
- 金融知识 → search_knowledge_base
- 最新新闻 → get_financial_news
- 实时信息 → search_web

**禁止直接回答，必须先调用工具获取数据！**
"""
    else:
        # 有具体计划，明确指示
        tool_list = "\n".join([
            f"- {t['tool']}({', '.join(f'{k}={v}' for k, v in t.get('params', {}).items())}) - {t.get('purpose', '')}"
            for t in tool_plan
        ])
        
        enforcement_msg = f"""
⚠️ 协调器分析：{reasoning}

📋 必须执行的工具调用计划（共 {len(tool_plan)} 个）：
{tool_list}

**请严格按照计划调用所有工具，调用完成后再生成答案。**
"""
    
    # 将强制指令添加到消息中
    messages = state["messages"]
    messages.append(SystemMessage(content=enforcement_msg))
    
    return {"messages": messages}


def validate_tool_execution(state: dict) -> dict:
    """
    验证工具执行情况：对比协调器规划的工具与实际执行的工具。
    
    - 统计已执行的工具（去重，保留参数）
    - 计算缺失的工具（计划中有但未执行）
    - 计算额外的工具（未在计划中但被执行）
    - 生成结构化报告，并追加系统消息，方便后续审计和回答引用
    """
    tool_plan = state.get("tool_plan", []) or []
    executed_tools = state.get("executed_tools", []) or []
    
    planned_names = [t.get("tool", "") for t in tool_plan if t.get("tool")]
    executed_names = [t.get("tool", "") for t in executed_tools if t.get("tool")]
    
    planned_set = set(planned_names)
    executed_set = set(executed_names)
    
    missing = sorted(planned_set - executed_set)
    extra = sorted(executed_set - planned_set)
    
    # 构造 Markdown 报告，供系统消息和前端展示
    lines = ["## 工具执行验证结果"]
    
    if not tool_plan:
        lines.append("- 协调器未给出明确的工具调用计划。")
    else:
        lines.append(f"- 协调器规划工具数量：{len(planned_names)}")
        if planned_names:
            lines.append(f"- 规划工具列表：{', '.join(planned_names)}")
    
    if executed_tools:
        lines.append(f"- 实际执行工具数量：{len(executed_names)}")
        lines.append(f"- 实际执行工具列表：{', '.join(executed_names)}")
    else:
        lines.append("- 实际未执行任何工具。")
    
    if missing:
        lines.append(f"- ⚠️ 未执行但在计划中的工具：{', '.join(missing)}")
    if extra:
        lines.append(f"- ℹ️ 未在计划中但被执行的工具：{', '.join(extra)}")
    if not missing and not extra and tool_plan:
        lines.append("- ✅ 实际执行与计划完全一致。")
    
    report_markdown = "\n".join(lines)
    
    # 将报告记录到状态中，并追加系统消息，供最终回答参考
    messages = state.get("messages", [])
    messages.append(SystemMessage(content=report_markdown))
    
    return {
        "messages": messages,
        "tool_validation": {
            "planned_tools": planned_names,
            "executed_tools": executed_names,
            "missing_tools": missing,
            "extra_tools": extra,
        },
    }
