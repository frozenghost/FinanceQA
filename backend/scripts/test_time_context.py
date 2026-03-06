"""Test time-context functionality."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from prompts.loader import load_system_prompt
from core.agent.coordinator import get_time_context


def test_time_context():
    """Test time context generation."""
    print("=" * 60)
    print("Coordinator time context")
    print("=" * 60)
    context = get_time_context()
    print(context)
    print()


def test_system_prompt():
    """Test time info in system prompt."""
    print("=" * 60)
    print("System prompt (first 500 chars)")
    print("=" * 60)
    prompt = load_system_prompt(strict=True)
    print(prompt[:500])
    print("\n...\n")
    print("=" * 60)
    print(f"Full prompt length: {len(prompt)} chars")
    print("=" * 60)


if __name__ == "__main__":
    test_time_context()
    print()
    test_system_prompt()
