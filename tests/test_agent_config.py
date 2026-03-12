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
