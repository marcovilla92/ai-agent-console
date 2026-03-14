"""Tests for Phase 24: Pipeline Extension (PIPE-01 through PIPE-05)."""
import json

from src.agents.config import (
    AGENT_REGISTRY,
    ROUTING_SECTIONS,
    build_agent_descriptions,
    build_agent_enum,
    validate_transition,
)
from src.pipeline.orchestrator import ORCHESTRATOR_SCHEMA


class TestDynamicSchema:
    """PIPE-01: Orchestrator JSON schema enum generated from AGENT_REGISTRY."""

    def test_schema_includes_all_registry_agents(self):
        schema = json.loads(ORCHESTRATOR_SCHEMA)
        enum_values = schema["properties"]["next_agent"]["enum"]
        for agent_name in AGENT_REGISTRY:
            assert agent_name in enum_values

    def test_schema_includes_approved(self):
        schema = json.loads(ORCHESTRATOR_SCHEMA)
        enum_values = schema["properties"]["next_agent"]["enum"]
        assert "approved" in enum_values

    def test_schema_includes_test_agent(self):
        schema = json.loads(ORCHESTRATOR_SCHEMA)
        enum_values = schema["properties"]["next_agent"]["enum"]
        assert "test" in enum_values

    def test_build_agent_enum_sorted(self):
        result = build_agent_enum()
        assert result == sorted(result)


class TestDynamicDescriptions:
    """PIPE-02: Orchestrator system prompt lists agents dynamically."""

    def test_descriptions_include_all_agents(self):
        desc = build_agent_descriptions()
        for agent_name in AGENT_REGISTRY:
            assert agent_name.upper() in desc

    def test_descriptions_have_content(self):
        desc = build_agent_descriptions()
        assert len(desc) > 50


class TestRoutingValidation:
    """PIPE-03: Invalid routing transitions fall back to next_agent."""

    def test_valid_execute_to_test(self):
        assert validate_transition("execute", "test") == "test"

    def test_valid_execute_to_review(self):
        assert validate_transition("execute", "review") == "review"

    def test_valid_review_to_plan(self):
        assert validate_transition("review", "plan") == "plan"

    def test_valid_review_to_execute(self):
        assert validate_transition("review", "execute") == "execute"

    def test_valid_test_to_review(self):
        assert validate_transition("test", "review") == "review"

    def test_valid_test_to_execute(self):
        assert validate_transition("test", "execute") == "execute"

    def test_invalid_review_to_test_fallback(self):
        # review -> test is not allowed; should fall back to None -> "approved"
        result = validate_transition("review", "test")
        assert result != "test"

    def test_invalid_plan_to_review_fallback(self):
        # plan -> review is not allowed; should fall back to "execute"
        assert validate_transition("plan", "review") == "execute"

    def test_approved_always_valid(self):
        assert validate_transition("review", "approved") == "approved"
        assert validate_transition("execute", "approved") == "approved"

    def test_unknown_from_agent_passthrough(self):
        assert validate_transition("unknown", "plan") == "plan"


class TestTestAgent:
    """PIPE-04: Test agent exists in registry with static review prompt."""

    def test_test_agent_in_registry(self):
        assert "test" in AGENT_REGISTRY

    def test_test_agent_has_system_prompt(self):
        config = AGENT_REGISTRY["test"]
        assert "test_system.txt" in config.system_prompt_file

    def test_test_agent_next_is_review(self):
        config = AGENT_REGISTRY["test"]
        assert config.next_agent == "review"

    def test_test_agent_has_output_sections(self):
        config = AGENT_REGISTRY["test"]
        assert "FINDINGS" in config.output_sections
        assert "VERDICT" in config.output_sections

    def test_test_agent_in_routing_sections(self):
        assert "test" in ROUTING_SECTIONS


class TestPipelineFlow:
    """PIPE-05: Pipeline flow is plan -> execute -> [file_write] -> test -> review."""

    def test_plan_next_is_execute(self):
        assert AGENT_REGISTRY["plan"].next_agent == "execute"

    def test_execute_next_is_test(self):
        assert AGENT_REGISTRY["execute"].next_agent == "test"

    def test_test_next_is_review(self):
        assert AGENT_REGISTRY["test"].next_agent == "review"

    def test_review_next_is_none(self):
        assert AGENT_REGISTRY["review"].next_agent is None

    def test_all_agents_have_descriptions(self):
        for name, config in AGENT_REGISTRY.items():
            assert config.description, f"Agent {name} missing description"

    def test_all_agents_have_allowed_transitions(self):
        for name, config in AGENT_REGISTRY.items():
            assert config.allowed_transitions, f"Agent {name} missing allowed_transitions"
