"""Tests for agent configuration registry."""
import pytest
from src.agents.config import AGENT_REGISTRY, get_agent_config, AgentConfig


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
