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
    
    time_context = "## Current Time Information\n\n"
    time_context += "**Important**: When the user asks about \"latest\", \"recent\", \"today\" or other time-related questions, please base your answer on the actual times below, not on the model's training cutoff.\n\n"
    
    for display_name, tz_name in timezones.items():
        try:
            local_time = utc_now.astimezone(ZoneInfo(tz_name))
            time_context += f"- {display_name}: {local_time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        except Exception:
            time_context += f"- {display_name}: {utc_now.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
    
    time_context += f"\nCurrent Date: {utc_now.strftime('%Y-%m-%d')}\n"
    time_context += f"Day of Week: {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][utc_now.weekday()]}\n\n"
    
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
