"""
协调器节点 - 强制工具使用，减少模型幻觉

核心思想：
1. 在模型回答前，先由协调器分析问题并规划工具调用
2. 强制要求必须使用工具获取数据，禁止直接回答
3. 只有在工具调用完成后，才允许模型基于工具结果生成答案
"""

from typing import Literal
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from services.llm_client import LLMClient


# 协调器的系统提示
COORDINATOR_PROMPT = """你是一个工具调用协调器，负责分析用户问题并规划工具调用策略。

## 可用工具
1. **get_market_data(ticker)** - 获取股票实时行情（价格、涨跌幅、成交量等）
2. **get_technical_indicators(ticker, indicators)** - 计算技术指标（MA、RSI、MACD、布林带等）
3. **search_knowledge_base(query)** - 搜索金融知识库（概念解释、财务数据、公司信息）
4. **get_financial_news(query, max_results)** - 获取最新金融新闻
5. **search_web(query)** - 网络搜索最新信息

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
- 涉及具体股票代码/公司名 → 必须调用 get_market_data 或 search_knowledge_base
- 询问技术指标/走势分析 → 必须调用 get_technical_indicators
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
            "coordinator_raw_output": raw_output,  # 保存原始输出供前端显示
        }
    except Exception as e:
        # 解析失败，默认需要工具
        print(f"协调器输出解析失败: {e}")
        return {
            "tool_plan": [],
            "needs_tools": True,
            "coordination_reasoning": "协调器解析失败，将由 agent 自行判断",
            "coordinator_raw_output": response.content if hasattr(response, 'content') else "",
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
    
    if not tool_plan:
        # 没有具体计划，但仍需要工具，给出通用指导
        enforcement_msg = """
⚠️ 协调器判断：此问题需要使用工具获取数据

请根据问题类型选择合适的工具：
- 股票行情 → get_market_data
- 技术指标 → get_technical_indicators  
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

📋 必须执行的工具调用计划：
{tool_list}

**请严格按照计划调用工具，禁止跳过或编造数据！**
"""
    
    # 将强制指令添加到消息中
    messages = state["messages"]
    messages.append(SystemMessage(content=enforcement_msg))
    
    return {"messages": messages}


def validate_tool_usage(state: dict) -> dict:
    """
    验证节点：检查 agent 是否真的使用了工具
    
    如果 agent 没有使用工具就直接回答，则拒绝并要求重新调用工具
    """
    messages = state["messages"]
    
    # 检查最近的消息中是否有工具调用
    recent_messages = messages[-5:]  # 检查最近5条消息
    has_tool_calls = any(
        hasattr(m, "tool_calls") and m.tool_calls
        for m in recent_messages
        if isinstance(m, AIMessage)
    )
    
    tool_plan = state.get("tool_plan", [])
    needs_tools = state.get("needs_tools", True)
    
    # 如果需要工具但没有调用，则添加警告
    if (needs_tools or tool_plan) and not has_tool_calls:
        warning_msg = SystemMessage(
            content="❌ 检测到你没有使用工具就直接回答了！这违反了协调器的要求。请重新调用必要的工具获取数据。"
        )
        messages.append(warning_msg)
        return {"messages": messages, "validation_failed": True}
    
    return {"validation_failed": False}
