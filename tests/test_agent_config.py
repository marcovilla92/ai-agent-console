"""Tests for agent configuration registry."""
from unittest.mock import patch

import pytest
from src.agents.config import AGENT_REGISTRY, get_agent_config, AgentConfig, resolve_pipeline_order


def test_registry_contains_all_agents():
    assert "plan" in AGENT_REGISTRY
    assert "execute" in AGENT_REGISTRY
    assert "review" in AGENT_REGISTRY


def test_get_agent_config_returns_config():
    cfg = get_agent_config("plan")
    assert isinstance(cfg, AgentConfig)
    assert cfg.name == "plan"


def test_get_agent_config_unknown_raises():
    with pytest.raises(KeyError, match="Unknown agent"):
        get_agent_config("nonexistent")


def test_plan_config_sections():
    cfg = get_agent_config("plan")
    assert "GOAL" in cfg.output_sections
    assert "HANDOFF" in cfg.output_sections
    assert cfg.next_agent == "execute"


def test_execute_config_sections():
    cfg = get_agent_config("execute")
    assert "TARGET" in cfg.output_sections
    assert "CODE" in cfg.output_sections
    assert cfg.next_agent == "review"


def test_review_config_sections():
    cfg = get_agent_config("review")
    assert "DECISION" in cfg.output_sections
    assert cfg.next_agent is None


def test_agent_config_is_frozen():
    cfg = get_agent_config("plan")
    with pytest.raises(AttributeError):
        cfg.name = "changed"


def test_resolve_pipeline_order_default():
    """Default start walks plan -> execute -> review."""
    assert resolve_pipeline_order() == ["plan", "execute", "review"]


def test_resolve_pipeline_order_from_execute():
    """Starting from execute walks execute -> review."""
    assert resolve_pipeline_order("execute") == ["execute", "review"]


def test_resolve_pipeline_order_unknown_agent():
    """Unknown start_agent raises KeyError."""
    with pytest.raises(KeyError):
        resolve_pipeline_order("nonexistent")


def test_resolve_pipeline_order_circular_detection():
    """Circular next_agent chain raises ValueError."""
    circular_registry = {
        "a": AgentConfig(name="a", system_prompt_file="a.txt", next_agent="b"),
        "b": AgentConfig(name="b", system_prompt_file="b.txt", next_agent="a"),
    }
    with patch.dict("src.agents.config.AGENT_REGISTRY", circular_registry, clear=True):
        with pytest.raises(ValueError, match="Circular next_agent chain detected"):
            resolve_pipeline_order("a")


# --- v2.4: Extended AgentConfig fields ---


def test_agentconfig_new_fields_with_defaults():
    """New fields have sensible defaults so existing instantiation still works."""
    cfg = AgentConfig(name="x", system_prompt_file="y.txt")
    assert cfg.system_prompt_inline is None
    assert cfg.source == "default"
    assert cfg.file_path is None


def test_agentconfig_new_fields_explicit():
    """All new fields can be set explicitly."""
    cfg = AgentConfig(
        name="x",
        system_prompt_file="y.txt",
        system_prompt_inline="You are a helper.",
        source="project",
        file_path="/tmp/agents/x.md",
    )
    assert cfg.system_prompt_inline == "You are a helper."
    assert cfg.source == "project"
    assert cfg.file_path == "/tmp/agents/x.md"


def test_agentconfig_frozen_new_fields():
    """New fields are also frozen."""
    cfg = AgentConfig(name="x", system_prompt_file="y.txt", source="project")
    with pytest.raises(AttributeError):
        cfg.source = "default"


def test_existing_registry_agents_have_default_new_fields():
    """Core registry agents use default values for new fields."""
    for name, cfg in AGENT_REGISTRY.items():
        assert cfg.system_prompt_inline is None, f"{name} should have None inline"
        assert cfg.source == "default", f"{name} should have source='default'"
        assert cfg.file_path is None, f"{name} should have None file_path"
