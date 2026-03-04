"""Load and merge system prompt with skill-specific prompt.txt files."""

from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"


def load_system_prompt() -> str:
    """
    Build the full system prompt by combining:
    1. Base ReAct agent prompt (react_agent.txt)
    2. Each skill's prompt.txt (if present)
    """
    base_path = Path(__file__).parent / "react_agent.txt"
    base = base_path.read_text(encoding="utf-8")

    skill_prompts: list[str] = []
    for p in sorted(SKILLS_DIR.rglob("prompt.md")):
        skill_name = p.parent.name
        content = p.read_text(encoding="utf-8").strip()
        if content:
            skill_prompts.append(f"# {skill_name}\n{content}")

    if skill_prompts:
        return base + "\n\n---\n\n" + "\n\n".join(skill_prompts)
    return base
