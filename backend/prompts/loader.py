"""Load and merge system prompt with skill-specific prompt.md files."""

from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"
PROMPTS_DIR = Path(__file__).parent


def load_system_prompt(strict: bool = False) -> str:
    """
    Build the full system prompt by combining:
    1. Base ReAct agent prompt (react_agent.md or react_agent_strict.md)
    2. Each skill's prompt.md (if present)

    Args:
        strict: If True, use react_agent_strict.md (enforce tool use, no hallucination).
    """
    prompt_file = "react_agent_strict.md" if strict else "react_agent.md"
    base_path = PROMPTS_DIR / prompt_file
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
