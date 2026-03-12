"""Tests for agent implementations: prompts, configs, and factory."""
from pathlib import Path

import pytest

from src.agents.config import AGENT_REGISTRY, PROMPTS_DIR
from src.agents.factory import create_agent
from src.agents.base import BaseAgent


def test_all_prompt_files_exist():
    for name, cfg in AGENT_REGISTRY.items():
        path = Path(cfg.system_prompt_file)
        assert path.exists(), f"Prompt file missing for {name}: {path}"


def test_plan_prompt_contains_required_sections():
    text = (PROMPTS_DIR / "plan_system.txt").read_text()
    for section in ["GOAL:", "ASSUMPTIONS:", "CONSTRAINTS:", "TASKS:", "ARCHITECTURE:", "FILES TO CREATE:", "HANDOFF:"]:
        assert section in text, f"Plan prompt missing section: {section}"


def test_execute_prompt_contains_required_sections():
    text = (PROMPTS_DIR / "execute_system.txt").read_text()
    for section in ["TARGET:", "PROJECT STRUCTURE:", "FILES:", "CODE:", "COMMANDS:", "SETUP NOTES:", "HANDOFF:"]:
        assert section in text, f"Execute prompt missing section: {section}"


def test_review_prompt_contains_required_sections():
    text = (PROMPTS_DIR / "review_system.txt").read_text()
    for section in ["SUMMARY:", "ISSUES:", "RISKS:", "IMPROVEMENTS:", "DECISION:"]:
        assert section in text, f"Review prompt missing section: {section}"


def test_review_prompt_contains_decision_values():
    text = (PROMPTS_DIR / "review_system.txt").read_text()
    assert "APPROVED" in text
    assert "BACK TO PLAN" in text
    assert "BACK TO EXECUTE" in text


async def test_factory_creates_plan_agent(db_conn, tmp_path):
    agent = create_agent("plan", db_conn, str(tmp_path))
    assert isinstance(agent, BaseAgent)
    assert agent.config.name == "plan"


async def test_factory_creates_all_agents(db_conn, tmp_path):
    for name in AGENT_REGISTRY:
        agent = create_agent(name, db_conn, str(tmp_path))
        assert agent.config.name == name


def test_factory_unknown_agent_raises(tmp_path):
    # db_conn not needed since it should raise before using it
    with pytest.raises(KeyError, match="Unknown agent"):
        create_agent("nonexistent", None, str(tmp_path))
