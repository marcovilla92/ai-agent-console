"""Tests for handoff builder."""
from src.agents.base import AgentResult
from src.pipeline.handoff import build_handoff


def test_handoff_includes_source_agent():
    result = AgentResult(
        agent_name="plan",
        raw_output="raw",
        sections={"GOAL": "Build something", "HANDOFF": "Ready for execute"},
        handoff="Ready for execute",
    )
    handoff = build_handoff(result)
    assert "HANDOFF FROM PLAN" in handoff


def test_handoff_includes_sections():
    result = AgentResult(
        agent_name="plan",
        raw_output="raw",
        sections={"GOAL": "Build an API", "TASKS": "1. Do things", "HANDOFF": "Go"},
        handoff="Go",
    )
    handoff = build_handoff(result)
    assert "--- GOAL ---" in handoff
    assert "Build an API" in handoff
    assert "--- TASKS ---" in handoff


def test_handoff_excludes_handoff_section_from_body():
    result = AgentResult(
        agent_name="plan",
        raw_output="raw",
        sections={"GOAL": "Test", "HANDOFF": "Notes here"},
        handoff="Notes here",
    )
    handoff = build_handoff(result)
    # HANDOFF appears in the header and notes, but not as a section divider
    assert "--- HANDOFF ---" not in handoff
    assert "Notes here" in handoff


def test_handoff_without_handoff_notes():
    result = AgentResult(
        agent_name="execute",
        raw_output="raw",
        sections={"TARGET": "REST API"},
        handoff=None,
    )
    handoff = build_handoff(result)
    assert "HANDOFF FROM EXECUTE" in handoff
    assert "--- TARGET ---" in handoff
    assert "Handoff notes:" not in handoff


def test_handoff_includes_timestamp():
    result = AgentResult(agent_name="plan", raw_output="", sections={}, handoff=None)
    handoff = build_handoff(result)
    assert "Timestamp:" in handoff
