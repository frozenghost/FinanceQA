"""
协调器节点 - 强制工具使用，减少模型幻觉

核心思想：
1. 在模型回答前，先由协调器分析问题并规划工具调用
2. 强制要求必须使用工具获取数据，禁止直接回答
3. 最后统计验证工具执行情况
"""

import json
import logging
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


# 协调器的系统提示
COORDINATOR_PROMPT = """你是一个工具调用协调器，负责分析用户问题并规划工具调用策略。

## 可用工具
1. **get_real_time_quote(ticker)** - 获取股票实时报价
2. **get_historical_prices(ticker, period?, start?, end?, interval?)** - 获取历史价格数据
   - period: 1d/5d/1mo/3mo/6mo/1y/2y/5y/max（与 start/end 二选一）
   - start/end: 指定日期范围，格式 YYYY-MM-DD（与 period 二选一）
   - interval: 1d(日线)/1wk(周线)/1mo(月线)
3. **get_company_fundamentals(ticker)** - 获取公司基本面和财务指标
4. **get_earnings_history(ticker)** - 获取财报历史数据
5. **calculate_technical_indicators(ticker, start, end, interval?)** - 计算技术指标和交易信号
   - start: 开始日期，格式 YYYY-MM-DD（必需）
   - end: 结束日期，格式 YYYY-MM-DD（必需）
   - interval: 1d(日线)/1wk(周线)/1mo(月线)
   - 注意：需要足够的数据点（建议至少20个交易日）
6. **get_financial_news(query, page_size)** - 获取最新金融新闻
7. **search_knowledge_base(query, top_k)** - 搜索金融知识库
8. **search_web(query, max_results)** - 实时网络搜索

## 你的任务
分析用户问题，判断需要调用哪些工具。

## 输出格式要求
你必须输出两部分内容：

1. **Markdown 格式的分析**（用于展示给用户）：
```markdown
## 分析
[你的分析推理过程，解释为什么需要这些工具]

## 工具调用计划
- **工具名**(参数) - 调用目的
- **工具名**(参数) - 调用目的
```

2. **JSON 格式的结构化数据**（用于程序处理，放在最后）：
```json
{
  "needs_tools": true/false,
  "reasoning": "简短的推理说明",
  "tool_plan": [
    {"tool": "工具名", "params": {"参数": "值"}, "purpose": "调用目的"}
  ]
}
```

## 判断规则
- 涉及具体股票代码/公司名 → 必须调用 get_real_time_quote 或 get_company_fundamentals
- 询问技术指标/走势分析 → 必须调用 calculate_technical_indicators
- 询问历史价格/K线数据 → 必须调用 get_historical_prices
- 询问最新新闻/事件 → 必须调用 get_financial_news 或 search_web
- 询问金融概念/术语 → 必须调用 search_knowledge_base
- 复合问题 → 规划多个工具调用

## 重要原则
- **禁止直接回答**：任何涉及具体数据的问题都必须通过工具获取
- **宁可多调用**：不确定时，多调用几个工具总比编造数据好
- 如果问题过于模糊，设置 needs_tools=false 并在 reasoning 中说明需要用户澄清

## 输出示例

### 示例 1：相对时间范围（最近X天）
```markdown
## 分析
用户询问 AAPL 最近 5 天的走势，需要获取历史价格数据。对于技术指标，需要扩展时间范围以获得足够的数据点（至少20个交易日）。

## 工具调用计划
- **get_historical_prices**(ticker=AAPL, period=5d, interval=1d) - 获取最近5个交易日的OHLCV数据用于展示
- **calculate_technical_indicators**(ticker=AAPL, start=2024-02-01, end=2024-03-05, interval=1d) - 计算技术指标（使用约1个月数据）
```

```json
{
  "needs_tools": true,
  "reasoning": "需要历史价格展示走势，技术指标需要更长时间范围",
  "tool_plan": [
    {"tool": "get_historical_prices", "params": {"ticker": "AAPL", "period": "5d", "interval": "1d"}, "purpose": "获取5日OHLCV数据"},
    {"tool": "calculate_technical_indicators", "params": {"ticker": "AAPL", "start": "2024-02-01", "end": "2024-03-05", "interval": "1d"}, "purpose": "计算技术指标"}
  ]
}
```

### 示例 2：指定日期范围
```markdown
## 分析
用户询问 TSLA 在 3月15日到3月21日期间的表现，需要获取该时间段的历史数据。技术指标需要更长的时间范围来计算。

## 工具调用计划
- **get_historical_prices**(ticker=TSLA, start=2024-03-15, end=2024-03-21, interval=1d) - 获取指定日期范围的OHLCV数据
- **calculate_technical_indicators**(ticker=TSLA, start=2024-02-01, end=2024-03-21, interval=1d) - 计算技术指标（扩展到2月初以获得足够数据）
```

```json
{
  "needs_tools": true,
  "reasoning": "需要指定日期范围的历史价格和技术指标",
  "tool_plan": [
    {"tool": "get_historical_prices", "params": {"ticker": "TSLA", "start": "2024-03-15", "end": "2024-03-21", "interval": "1d"}, "purpose": "获取指定日期范围的OHLCV数据"},
    {"tool": "calculate_technical_indicators", "params": {"ticker": "TSLA", "start": "2024-02-01", "end": "2024-03-21", "interval": "1d"}, "purpose": "计算技术指标"}
  ]
}
```
"""


def _state_to_messages(state: dict) -> list:
    """Build coordination messages from graph state (for LCEL chain)."""
    messages = state["messages"]
    last_user_message = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
        "",
    )
    time_context = get_time_context()
    full_prompt = time_context + "\n\n" + COORDINATOR_PROMPT
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
    校验协调器规划的工具与实际执行的工具是否一致。

    约定：
    - state["tool_plan"] 为协调器规划的工具列表
      [{"tool": "name", "params": {...}}, ...]
    - state["executed_tools"] 为实际执行的工具列表
      [{"tool": "name", "params": {...}}, ...]

    返回：
    - {"tool_validation": {...}} 将结果写回 state，供后续节点或前端使用
    """
    planned = state.get("tool_plan", []) or []
    executed = state.get("executed_tools", []) or []

    planned_names = [t.get("tool") for t in planned]
    executed_names = [t.get("tool") for t in executed]

    planned_set = set(planned_names)
    executed_set = set(executed_names)

    missing_tools = sorted(planned_set - executed_set)
    extra_tools = sorted(executed_set - planned_set)

    is_consistent = not missing_tools and not extra_tools

    summary = {
        "planned_tools": planned_names,
        "executed_tools": executed_names,
        "missing_tools": missing_tools,
        "extra_tools": extra_tools,
        "is_consistent": is_consistent,
    }

    if not is_consistent:
        logger.warning(f"工具执行与协调器规划不一致: {summary}")

    return {"tool_validation": summary}
