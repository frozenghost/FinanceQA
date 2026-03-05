"""
协调器节点 - 强制工具使用，减少模型幻觉

核心思想：
1. 在模型回答前，先由协调器分析问题并规划工具调用
2. 强制要求必须使用工具获取数据，禁止直接回答
3. 最后统计验证工具执行情况
"""

from typing import Literal
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
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
2. **get_historical_prices(ticker, period, interval)** - 获取历史价格数据
3. **get_company_fundamentals(ticker)** - 获取公司基本面和财务指标
4. **get_earnings_history(ticker)** - 获取财报历史数据
5. **calculate_technical_indicators(ticker, period)** - 计算技术指标和交易信号
6. **get_financial_news(query, page_size)** - 获取最新金融新闻
7. **search_knowledge_base(query, top_k)** - 搜索金融知识库
8. **search_web(query, max_results)** - 实时网络搜索

## 你的任务
分析用户问题，判断需要调用哪些工具。输出格式：

```json
{{
  "needs_tools": true/false,
  "reasoning": "为什么需要这些工具",
  "tool_plan": [
    {{"tool": "工具名", "params": {{"参数": "值"}}, "purpose": "调用目的"}}
  ]
}}
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
"""


async def coordinate_tools(state: dict) -> dict:
    """
    协调器节点：分析问题并规划工具调用
    
    返回：
    - tool_plan: 工具调用计划列表
    - needs_tools: 是否需要工具
    - coordination_reasoning: 协调器的推理过程
    """
    messages = state["messages"]
    last_user_message = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
        ""
    )
    
    # 调用 LLM 进行工具规划
    llm = LLMClient().get_langchain_model(role="coordinator")
    
    # 添加时间上下文
    time_context = get_time_context()
    full_prompt = time_context + "\n\n" + COORDINATOR_PROMPT
    
    coordination_messages = [
        SystemMessage(content=full_prompt),
        HumanMessage(content=f"用户问题：{last_user_message}\n\n请规划工具调用策略。")
    ]
    
    response = await llm.ainvoke(coordination_messages)
    
    # 解析协调器的输出
    import json
    try:
        # 提取 JSON（可能被包裹在 ```json ``` 中）
        content = response.content
        
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        plan = json.loads(content)
        
        tool_plan = plan.get("tool_plan", [])
        logger.info(f"协调器规划: {len(tool_plan)} 个工具")
        
        return {
            "tool_plan": tool_plan,
            "needs_tools": plan.get("needs_tools", True),
            "coordination_reasoning": plan.get("reasoning", ""),
        }
    except Exception as e:
        # 解析失败，默认需要工具
        logger.error(f"协调器输出解析失败: {e}")
        return {
            "tool_plan": [],
            "needs_tools": True,
            "coordination_reasoning": "协调器解析失败，将由 agent 自行判断",
        }


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
