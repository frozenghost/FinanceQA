"""Integration tests for the LangGraph agent."""

import pytest
from unittest.mock import patch, MagicMock


class TestAgentState:
    """Tests for the AgentState schema (LangGraph state is dict-like)."""

    def test_state_has_required_fields(self):
        """AgentState should have ticker, query_type, cache_hits fields."""
        from core.agent.state import AgentState

        state = AgentState(messages=[], ticker="AAPL", query_type="market", cache_hits=0)
        assert state["ticker"] == "AAPL"
        assert state["query_type"] == "market"
        assert state["cache_hits"] == 0

    def test_state_defaults(self):
        """AgentState optional fields should default correctly."""
        from core.agent.state import AgentState

        state = AgentState(messages=[])
        assert state.get("ticker") is None
        assert state.get("query_type") is None
        assert state.get("cache_hits", 0) == 0


class TestPromptLoader:
    """Tests for the prompt loading system."""

    def test_load_system_prompt_returns_string(self):
        """System prompt should be a non-empty string."""
        from prompts.loader import load_system_prompt

        prompt = load_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100  # Should have substantial content

    def test_system_prompt_includes_skills(self):
        """System prompt should include skill-specific sections."""
        from prompts.loader import load_system_prompt

        prompt = load_system_prompt()
        # Should contain skill names from prompt.md files
        assert "market_data" in prompt
        assert "research" in prompt


class TestSkillsRegistry:
    """Tests for the skill registry."""

    def test_all_tools_not_empty(self):
        """ALL_TOOLS should contain at least the 5 defined skills."""
        from skills import ALL_TOOLS

        assert len(ALL_TOOLS) >= 5

    def test_all_tools_are_callable(self):
        """Each tool in ALL_TOOLS should be invokable (has invoke/ainvoke)."""
        from skills import ALL_TOOLS

        for tool in ALL_TOOLS:
            assert hasattr(tool, "ainvoke") or hasattr(tool, "invoke"), f"{tool} is not invokable"


class TestModelRouting:
    """Tests for model routing configuration."""

    def test_model_routing_has_required_roles(self):
        """MODEL_ROUTING should have market_analyst and coordinator."""
        from config.models import MODEL_ROUTING

        assert "market_analyst" in MODEL_ROUTING
        assert "coordinator" in MODEL_ROUTING

    def test_model_routing_values_are_strings(self):
        """All model routing values should be non-empty strings."""
        from config.models import MODEL_ROUTING

        for role, model in MODEL_ROUTING.items():
            assert isinstance(model, str), f"{role} model should be a string"
            assert len(model) > 0, f"{role} model should not be empty"
