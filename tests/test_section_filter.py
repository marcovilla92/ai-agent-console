"""Tests for orchestrator section filtering (CTX-08)."""
from src.agents.config import ROUTING_SECTIONS
from src.pipeline.orchestrator import OrchestratorState, build_orchestrator_prompt


class TestSectionFiltering:
    def _make_state(self, agent: str) -> OrchestratorState:
        state = OrchestratorState(session_id=1, original_prompt="test")
        state.current_agent = agent
        return state

    def test_routing_sections_map_exists(self):
        assert "plan" in ROUTING_SECTIONS
        assert "execute" in ROUTING_SECTIONS
        assert "review" in ROUTING_SECTIONS

    def test_execute_code_filtered_from_routing(self):
        state = self._make_state("execute")
        sections = {
            "TARGET": "Build something",
            "CODE": "```python\nprint('huge code block')\n```" * 100,
            "HANDOFF": "Ready for review",
        }
        prompt = build_orchestrator_prompt(state, sections)
        assert "Build something" in prompt
        assert "Ready for review" in prompt
        assert "huge code block" not in prompt

    def test_review_all_sections_included(self):
        state = self._make_state("review")
        sections = {
            "SUMMARY": "Looks good",
            "ISSUES": "None",
            "DECISION": "APPROVED",
        }
        prompt = build_orchestrator_prompt(state, sections)
        assert "Looks good" in prompt
        assert "APPROVED" in prompt

    def test_plan_filters_irrelevant_sections(self):
        state = self._make_state("plan")
        sections = {
            "GOAL": "Build API",
            "TASKS": "1. Setup\n2. Implement",
            "HANDOFF": "Ready",
            "RANDOM": "Should be filtered",
        }
        prompt = build_orchestrator_prompt(state, sections)
        assert "Build API" in prompt
        assert "Should be filtered" not in prompt

    def test_unknown_agent_includes_all(self):
        state = self._make_state("unknown_agent")
        sections = {"FOO": "bar", "BAZ": "qux"}
        prompt = build_orchestrator_prompt(state, sections)
        assert "bar" in prompt
        assert "qux" in prompt
