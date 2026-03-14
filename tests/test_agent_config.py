"""Tests for agent configuration registry."""
import logging
from unittest.mock import patch

import pytest
from src.agents.config import (
    AGENT_REGISTRY,
    AgentConfig,
    DEFAULT_REGISTRY,
    PROTECTED_AGENTS,
    build_agent_descriptions,
    build_agent_enum,
    get_agent_config,
    get_project_registry,
    inject_commands_as_agents,
    merge_registries,
    resolve_pipeline_order,
    validate_transition,
)


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


# --- v2.4 Plan 02: Registry merge and core protection ---


def _make_project_agent(name: str) -> AgentConfig:
    """Helper to create a project agent config."""
    return AgentConfig(
        name=name,
        system_prompt_file="",
        system_prompt_inline=f"You are {name}.",
        description=f"Project agent: {name}",
        source="project",
    )


class TestDefaultRegistryAlias:
    """DEFAULT_REGISTRY is the canonical name; AGENT_REGISTRY is backward-compat."""

    def test_default_registry_exists(self):
        assert DEFAULT_REGISTRY is not None
        assert len(DEFAULT_REGISTRY) == 4

    def test_agent_registry_is_alias(self):
        assert AGENT_REGISTRY is DEFAULT_REGISTRY


class TestProtectedAgents:
    """PROTECTED_AGENTS frozenset contains the four core agent names."""

    def test_protected_agents_contents(self):
        assert PROTECTED_AGENTS == frozenset({"plan", "execute", "test", "review"})

    def test_protected_agents_is_frozenset(self):
        assert isinstance(PROTECTED_AGENTS, frozenset)


class TestMergeRegistries:
    """merge_registries() creates new dict, protects core agents."""

    def test_merge_adds_project_agents(self):
        """Project agents 'db-migrator' and 'api-tester' appear in merged result."""
        project = {
            "db-migrator": _make_project_agent("db-migrator"),
            "api-tester": _make_project_agent("api-tester"),
        }
        merged = merge_registries(DEFAULT_REGISTRY, project)
        assert "db-migrator" in merged
        assert "api-tester" in merged
        # Core agents still present
        for core in ("plan", "execute", "test", "review"):
            assert core in merged

    def test_core_agents_protected(self):
        """A project agent named 'plan' is skipped; original core 'plan' remains."""
        project = {"plan": _make_project_agent("plan")}
        merged = merge_registries(DEFAULT_REGISTRY, project)
        assert merged["plan"].source == "default"

    def test_core_override_logs_warning(self, caplog):
        """Merging a project agent named 'execute' logs a warning."""
        project = {"execute": _make_project_agent("execute")}
        with caplog.at_level(logging.WARNING):
            merge_registries(DEFAULT_REGISTRY, project)
        assert any("conflicts with core agent" in r.message for r in caplog.records)

    def test_default_registry_unchanged(self):
        """After merge, DEFAULT_REGISTRY still has exactly 4 agents with source='default'."""
        project = {"custom": _make_project_agent("custom")}
        merge_registries(DEFAULT_REGISTRY, project)
        assert len(DEFAULT_REGISTRY) == 4
        for cfg in DEFAULT_REGISTRY.values():
            assert cfg.source == "default"

    def test_merge_returns_new_dict(self):
        """Merged result is a new dict, not the same object as default."""
        merged = merge_registries(DEFAULT_REGISTRY, {})
        assert merged is not DEFAULT_REGISTRY


class TestGetProjectRegistry:
    """get_project_registry() returns isolated per-project registries."""

    def test_project_registry_is_isolated(self):
        """Modifying returned registry does not affect DEFAULT_REGISTRY."""
        with patch("src.agents.loader.discover_project_agents", return_value={
            "custom": _make_project_agent("custom"),
        }):
            reg = get_project_registry("/some/path")
            reg["hacked"] = _make_project_agent("hacked")
            assert "hacked" not in DEFAULT_REGISTRY
            assert "custom" not in DEFAULT_REGISTRY

    def test_get_project_registry_no_path(self):
        """get_project_registry(None) returns copy of DEFAULT_REGISTRY."""
        reg = get_project_registry(None)
        assert reg == dict(DEFAULT_REGISTRY)
        assert reg is not DEFAULT_REGISTRY

    def test_get_project_registry_no_agents_dir(self):
        """get_project_registry('/nonexistent') returns copy of DEFAULT_REGISTRY."""
        reg = get_project_registry("/nonexistent")
        assert reg == dict(DEFAULT_REGISTRY)


class TestRegistryAwareFunctions:
    """Functions accept optional registry parameter."""

    def test_build_agent_enum_with_custom_registry(self):
        custom = {"alpha": _make_project_agent("alpha")}
        result = build_agent_enum(registry=custom)
        assert "alpha" in result
        assert "approved" in result
        assert "plan" not in result

    def test_build_agent_descriptions_with_custom_registry(self):
        custom = {"alpha": _make_project_agent("alpha")}
        result = build_agent_descriptions(registry=custom)
        assert "ALPHA" in result
        assert "PLAN" not in result

    def test_validate_transition_with_custom_registry(self):
        custom = {
            "alpha": AgentConfig(
                name="alpha", system_prompt_file="",
                allowed_transitions=("beta",), next_agent="beta",
            ),
            "beta": _make_project_agent("beta"),
        }
        assert validate_transition("alpha", "beta", registry=custom) == "beta"

    def test_get_agent_config_with_custom_registry(self):
        custom = {"alpha": _make_project_agent("alpha")}
        cfg = get_agent_config("alpha", registry=custom)
        assert cfg.name == "alpha"

    def test_resolve_pipeline_order_with_custom_registry(self):
        custom = {
            "a": AgentConfig(name="a", system_prompt_file="", next_agent="b"),
            "b": AgentConfig(name="b", system_prompt_file="", next_agent=None),
        }
        assert resolve_pipeline_order("a", registry=custom) == ["a", "b"]


# --- Phase 28: inject_commands_as_agents ---


class TestInjectCommandsAsAgents:
    """inject_commands_as_agents converts CommandInfo dicts into AgentConfig entries."""

    def test_adds_cmd_prefixed_entries(self, tmp_path):
        """Commands are added with cmd- prefix and source='command'."""
        from src.commands.loader import CommandInfo

        cmd_file = tmp_path / "migrate.md"
        cmd_file.write_text("Run database migrations")

        commands = {
            "migrate": CommandInfo(
                name="migrate",
                description="Run database migrations",
                file_path=str(cmd_file),
            ),
        }
        result = inject_commands_as_agents(dict(DEFAULT_REGISTRY), commands)
        assert "cmd-migrate" in result
        cfg = result["cmd-migrate"]
        assert cfg.source == "command"
        assert cfg.name == "cmd-migrate"
        assert "database migrations" in cfg.description.lower()

    def test_does_not_overwrite_existing(self, tmp_path):
        """Existing agent with same cmd-name is not overwritten."""
        from src.commands.loader import CommandInfo

        cmd_file = tmp_path / "plan.md"
        cmd_file.write_text("Some plan command")

        # Pre-populate registry with cmd-plan
        reg = dict(DEFAULT_REGISTRY)
        reg["cmd-plan"] = AgentConfig(
            name="cmd-plan", system_prompt_file="", source="default",
        )
        commands = {
            "plan": CommandInfo(
                name="plan",
                description="A plan command",
                file_path=str(cmd_file),
            ),
        }
        result = inject_commands_as_agents(reg, commands)
        assert result["cmd-plan"].source == "default"  # original preserved

    def test_empty_commands_returns_unchanged(self):
        """Empty commands dict returns registry unchanged (copy)."""
        reg = dict(DEFAULT_REGISTRY)
        result = inject_commands_as_agents(reg, {})
        assert result == reg
        assert result is not reg  # new dict

    def test_does_not_mutate_input(self, tmp_path):
        """Input registry is not mutated."""
        from src.commands.loader import CommandInfo

        cmd_file = tmp_path / "deploy.md"
        cmd_file.write_text("Deploy to production")

        original = dict(DEFAULT_REGISTRY)
        original_len = len(original)
        commands = {
            "deploy": CommandInfo(
                name="deploy",
                description="Deploy to production",
                file_path=str(cmd_file),
            ),
        }
        inject_commands_as_agents(original, commands)
        assert len(original) == original_len
