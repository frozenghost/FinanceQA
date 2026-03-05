"""Load and merge system prompt with skill-specific prompt.md files."""

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

SKILLS_DIR = Path(__file__).parent.parent / "skills"
PROMPTS_DIR = Path(__file__).parent


def load_system_prompt(strict: bool = False) -> str:
    """
    Build the full system prompt by combining:
    1. Current time context (for understanding "latest", "recent", etc.)
    2. Base ReAct agent prompt (react_agent.md or react_agent_strict.md)
    3. Each skill's prompt.md (if present)

    Args:
        strict: If True, use react_agent_strict.md (enforce tool use, no hallucination).
    """
    # Get current time in multiple timezones for context
    utc_now = datetime.now(ZoneInfo("UTC"))
    
    # Common timezones for financial markets
    timezones = {
        "UTC": "UTC",
        "US/Eastern": "America/New_York",  # NYSE, NASDAQ
        "Asia/Shanghai": "Asia/Shanghai",  # Chinese markets
        "Asia/Hong_Kong": "Asia/Hong_Kong",  # HKEX
    }
    
    time_context = "## 当前时间信息\n\n"
    time_context += "**重要**：当用户询问\"最新\"、\"最近\"、\"今天\"等时间相关的问题时，请以下面的实际时间为准，而不是你的训练数据截止时间。\n\n"
    
    for display_name, tz_name in timezones.items():
        try:
            local_time = utc_now.astimezone(ZoneInfo(tz_name))
            time_context += f"- {display_name}: {local_time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        except Exception:
            # Fallback if timezone not available
            time_context += f"- {display_name}: {utc_now.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
    
    time_context += f"\n当前日期：{utc_now.strftime('%Y年%m月%d日')}\n"
    time_context += f"当前星期：{['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日'][utc_now.weekday()]}\n\n"
    
    # Load base prompt
    prompt_file = "react_agent_strict.md" if strict else "react_agent.md"
    base_path = PROMPTS_DIR / prompt_file
    base = base_path.read_text(encoding="utf-8")

    skill_prompts: list[str] = []
    for p in sorted(SKILLS_DIR.rglob("prompt.md")):
        skill_name = p.parent.name
        content = p.read_text(encoding="utf-8").strip()
        if content:
            skill_prompts.append(f"# {skill_name}\n{content}")

    # Combine: time context + base prompt + skill prompts
    full_prompt = time_context + "\n---\n\n" + base
    if skill_prompts:
        full_prompt += "\n\n---\n\n" + "\n\n".join(skill_prompts)
    
    return full_prompt
