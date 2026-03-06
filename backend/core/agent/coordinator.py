"""
Coordinator node — enforce tool usage and reduce model hallucinations.

Core ideas:
1. Before the model answers, the coordinator analyzes the question and plans tool calls.
2. Enforce that tools must be used to fetch data; direct answering with invented data is forbidden.
3. Finally, validate and summarize tool execution.
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
    """Generate current time context information."""
    utc_now = datetime.now(ZoneInfo("UTC"))
    
    timezones = {
        "UTC": "UTC",
        "US/Eastern": "America/New_York",
        "Asia/Shanghai": "Asia/Shanghai",
        "Asia/Hong_Kong": "Asia/Hong_Kong",
    }
    
    time_info = "## Current time\n"
    for display_name, tz_name in timezones.items():
        try:
            local_time = utc_now.astimezone(ZoneInfo(tz_name))
            time_info += f"- {display_name}: {local_time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        except Exception:
            time_info += f"- {display_name}: {utc_now.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
    
    time_info += (
        "\n**Important**: When the user asks about \"latest\" or \"recent\" data, "
        "you must base your answer on the actual times above, not on the model's training cutoff.\n"
    )
    return time_info


def load_coordinator_prompt() -> str:
    """Load the coordinator prompt template."""
    prompt_path = Path(__file__).parents[2] / "prompts" / "coordinator.md"
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to load coordinator prompt: {e}")
        # Basic fallback prompt (English)
        return (
            "You are a tool orchestration coordinator. Analyze the user's question and "
            "plan which tools to call.\n"
            "Output a JSON tool-call plan describing the tools and parameters you will use."
        )



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
        HumanMessage(
            content=(
                f"User question: {last_user_message}\n\n"
                "Please plan an appropriate tool-calling strategy."
            )
        ),
    ]


def _parse_coordinator_output(aimessage: AIMessage) -> dict:
    """Parse coordinator LLM output into a state update."""
    content = aimessage.content or ""
    
    # Store raw output for streaming (includes Markdown portion)
    raw_output = content
    
    try:
        # Extract the JSON part (assumed to be in the last code block)
        json_content = content
        if "```json" in content:
            # Find the last json code block
            parts = content.split("```json")
            if len(parts) > 1:
                json_content = parts[-1].split("```")[0].strip()
        elif "```" in content:
            # Fall back to the last generic code block
            parts = content.split("```")
            if len(parts) >= 3:
                json_content = parts[-2].strip()

        # Use json_repair.loads instead of json.loads to auto-repair and parse
        plan = json_repair.loads(json_content)
        tool_plan = plan.get("tool_plan", [])
        logger.info(f"Coordinator planned {len(tool_plan)} tool(s).")
        
        # Build stable Markdown from the structured plan (do not stream raw JSON directly)
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

        markdown_parts = ["## Analysis"]
        if reasoning_text:
            markdown_parts.append(reasoning_text)
        markdown_parts.append("")  # blank line
        if tool_plan_md_lines:
            markdown_parts.append("## Tool call plan")
            markdown_parts.extend(tool_plan_md_lines)
        markdown_content = "\n".join(markdown_parts).strip()
        
        return {
            "tool_plan": tool_plan,
            "needs_tools": plan.get("needs_tools", True),
            "coordination_reasoning": plan.get("reasoning", ""),
            "coordinator_raw_output": raw_output,  # Full output (Markdown + JSON)
            "coordinator_markdown": markdown_content,  # Markdown portion only
        }
    except Exception as e:
        logger.error(f"Failed to parse coordinator output: {e}")
        return {
            "tool_plan": [],
            "needs_tools": True,
            "coordination_reasoning": "Coordinator parsing failed; the agent will decide how to proceed.",
            "coordinator_raw_output": raw_output,
            "coordinator_markdown": raw_output,  # Fall back to raw output if parsing fails
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
    """Routing function: decide whether tools should be used."""
    needs_tools = state.get("needs_tools", True)
    tool_plan = state.get("tool_plan", [])
    
    # If the coordinator says tools are needed or there is a plan, use tools
    if needs_tools or tool_plan:
        return "use_tools"
    else:
        return "direct_answer"


def enforce_tool_usage(state: dict) -> dict:
    """
    Enforcement node: based on the coordinator plan, force the agent to use tools.
    """
    tool_plan = state.get("tool_plan", [])
    reasoning = state.get("coordination_reasoning", "")
    
    if not tool_plan:
        # No concrete plan but tools are still required; provide generic guidance
        enforcement_msg = """
⚠️ Coordinator decision: this question requires tools to fetch data.

Please choose appropriate tools based on the question type:
- Quotes → get_real_time_quote
- Historical prices → get_historical_prices
- Fundamentals → get_company_fundamentals
- Earnings → get_earnings_history
- Technical indicators → calculate_technical_indicators  
- Financial knowledge → search_knowledge_base
- Latest news → get_financial_news
- Real-time information → search_web

**Do not answer directly. You must call tools to fetch data first.**
"""
    else:
        # There is a concrete plan, give explicit instructions
        tool_list = "\n".join([
            f"- {t['tool']}({', '.join(f'{k}={v}' for k, v in t.get('params', {}).items())}) - {t.get('purpose', '')}"
            for t in tool_plan
        ])
        
        enforcement_msg = f"""
⚠️ Coordinator analysis: {reasoning}

📋 Required tool-call plan (total {len(tool_plan)}):
{tool_list}

**You must strictly follow this plan, call all tools, and only then generate an answer.**
"""
    
    # Append enforcement instructions as a system message
    messages = state["messages"]
    messages.append(SystemMessage(content=enforcement_msg))
    
    return {"messages": messages}


def validate_tool_execution(state: dict) -> dict:
    """
    Validate tool execution by comparing the coordinator plan with actually executed tools.
    
    - Count executed tools (deduplicated, keeping parameters)
    - Find missing tools (planned but not executed)
    - Find extra tools (executed but not planned)
    - Generate a structured report and append it as a system message for auditing and reference
    """
    tool_plan = state.get("tool_plan", []) or []
    executed_tools = state.get("executed_tools", []) or []
    
    planned_names = [t.get("tool", "") for t in tool_plan if t.get("tool")]
    executed_names = [t.get("tool", "") for t in executed_tools if t.get("tool")]
    
    planned_set = set(planned_names)
    executed_set = set(executed_names)
    
    missing = sorted(planned_set - executed_set)
    extra = sorted(executed_set - planned_set)
    
    # Build a Markdown report for system messages and frontend display
    lines = ["## Tool execution validation"]
    
    if not tool_plan:
        lines.append("- Coordinator did not provide a concrete tool-call plan.")
    else:
        lines.append(f"- Number of tools in coordinator plan: {len(planned_names)}")
        if planned_names:
            lines.append(f"- Planned tools: {', '.join(planned_names)}")
    
    if executed_tools:
        lines.append(f"- Number of executed tools: {len(executed_names)}")
        lines.append(f"- Executed tools: {', '.join(executed_names)}")
    else:
        lines.append("- No tools were actually executed.")
    
    if missing:
        lines.append(f"- ⚠️ Missing tools (planned but not executed): {', '.join(missing)}")
    if extra:
        lines.append(f"- ℹ️ Extra tools (executed but not in the plan): {', '.join(extra)}")
    if not missing and not extra and tool_plan:
        lines.append("- ✅ Executed tools exactly match the plan.")
    
    report_markdown = "\n".join(lines)
    
    # Save the report into state and append it as a system message for later reference
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
