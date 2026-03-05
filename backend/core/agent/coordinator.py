"""
协调器节点 - 强制工具使用，减少模型幻觉

核心思想：
1. 在模型回答前，先由协调器分析问题并规划工具调用
2. 强制要求必须使用工具获取数据，禁止直接回答
3. 跟踪工具执行情况，确保计划与实际执行一致
"""

from typing import Literal
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from services.llm_client import LLMClient


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


def coordinate_tools(state: dict) -> dict:
    """
    协调器节点：分析问题并规划工具调用
    
    返回：
    - tool_plan: 工具调用计划列表
    - needs_tools: 是否需要工具
    - coordination_reasoning: 协调器的推理过程
    - coordinator_raw_output: 原始输出（用于前端显示）
    """
    messages = state["messages"]
    last_user_message = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
        ""
    )
    
    # 调用 LLM 进行工具规划
    llm = LLMClient().get_langchain_model(role="coordinator")
    
    coordination_messages = [
        SystemMessage(content=COORDINATOR_PROMPT),
        HumanMessage(content=f"用户问题：{last_user_message}\n\n请规划工具调用策略。")
    ]
    
    response = llm.invoke(coordination_messages)
    
    # 解析协调器的输出
    import json
    try:
        # 提取 JSON（可能被包裹在 ```json ``` 中）
        content = response.content
        raw_output = content  # 保存原始输出
        
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        plan = json.loads(content)
        
        return {
            "tool_plan": plan.get("tool_plan", []),
            "needs_tools": plan.get("needs_tools", True),
            "coordination_reasoning": plan.get("reasoning", ""),
            "coordinator_raw_output": raw_output,
            "executed_tools": [],  # 初始化已执行工具列表
            "retry_count": 0,      # 初始化重试计数
        }
    except Exception as e:
        # 解析失败，默认需要工具
        print(f"协调器输出解析失败: {e}")
        return {
            "tool_plan": [],
            "needs_tools": True,
            "coordination_reasoning": "协调器解析失败，将由 agent 自行判断",
            "coordinator_raw_output": response.content if hasattr(response, 'content') else "",
            "executed_tools": [],
            "retry_count": 0,
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
    
    这个节点会修改 system prompt，明确告知 agent 必须使用哪些工具
    """
    tool_plan = state.get("tool_plan", [])
    reasoning = state.get("coordination_reasoning", "")
    executed_tools = state.get("executed_tools", [])
    
    # 计算还需要执行的工具
    planned_tools = [t["tool"] for t in tool_plan]
    remaining_tools = [t for t in tool_plan if t["tool"] not in executed_tools]
    
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
    elif remaining_tools:
        # 有未完成的工具，明确指示
        tool_list = "\n".join([
            f"- {t['tool']}({', '.join(f'{k}={v}' for k, v in t.get('params', {}).items())}) - {t.get('purpose', '')}"
            for t in remaining_tools
        ])
        
        executed_info = ""
        if executed_tools:
            executed_info = f"\n✓ 已执行: {', '.join(executed_tools)}"
        
        enforcement_msg = f"""
⚠️ 协调器分析：{reasoning}

📋 工具调用计划（共 {len(planned_tools)} 个）：{executed_info}

🔄 待执行的工具：
{tool_list}

**请严格按照计划调用所有工具，不要跳过！调用完所有工具后再生成答案。**
"""
    else:
        # 所有工具都已执行，可以生成答案
        enforcement_msg = f"""
✓ 所有计划的工具已执行完毕（共 {len(executed_tools)} 个）

现在请基于工具返回的数据生成完整答案。
"""
    
    # 将强制指令添加到消息中
    messages = state["messages"]
    messages.append(SystemMessage(content=enforcement_msg))
    
    return {"messages": messages}


def validate_tool_usage(state: dict) -> dict:
    """
    验证节点：检查 agent 是否按计划执行了所有工具
    
    对比 tool_plan 和 executed_tools，确保一致性
    """
    messages = state["messages"]
    tool_plan = state.get("tool_plan", [])
    executed_tools = state.get("executed_tools", [])
    needs_tools = state.get("needs_tools", True)
    retry_count = state.get("retry_count", 0)
    
    # 如果不需要工具，直接通过
    if not needs_tools and not tool_plan:
        return {"validation_failed": False}
    
    # 检查是否有工具调用
    has_tool_calls = any(
        isinstance(m, AIMessage) and hasattr(m, "tool_calls") and m.tool_calls
        for m in messages[-10:]
    )
    
    # 如果完全没有工具调用
    if not has_tool_calls and (needs_tools or tool_plan):
        if retry_count >= 2:
            # 重试次数过多，放弃强制
            warning_msg = SystemMessage(
                content="⚠️ 多次尝试后仍未调用工具，将基于现有信息回答（可能不准确）"
            )
            messages.append(warning_msg)
            return {"messages": messages, "validation_failed": False}
        
        warning_msg = SystemMessage(
            content=f"❌ 检测到你没有使用工具就直接回答了！这违反了协调器的要求。\n\n请重新调用必要的工具获取数据。（重试 {retry_count + 1}/2）"
        )
        messages.append(warning_msg)
        return {
            "messages": messages,
            "validation_failed": True,
            "retry_count": retry_count + 1,
        }
    
    # 如果有具体的工具计划，检查是否都执行了
    if tool_plan:
        planned_tools = set(t["tool"] for t in tool_plan)
        executed_set = set(executed_tools)
        missing_tools = planned_tools - executed_set
        
        if missing_tools and retry_count < 2:
            missing_list = "\n".join([
                f"- {t['tool']}({', '.join(f'{k}={v}' for k, v in t.get('params', {}).items())})"
                for t in tool_plan if t["tool"] in missing_tools
            ])
            
            warning_msg = SystemMessage(
                content=f"""❌ 工具执行不完整！

计划调用 {len(planned_tools)} 个工具，实际只调用了 {len(executed_set)} 个。

缺失的工具：
{missing_list}

请补充调用这些工具。（重试 {retry_count + 1}/2）"""
            )
            messages.append(warning_msg)
            return {
                "messages": messages,
                "validation_failed": True,
                "retry_count": retry_count + 1,
            }
    
    # 验证通过
    return {"validation_failed": False}
