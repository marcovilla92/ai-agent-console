"""
Tests for TaskContext Protocol conformance and orchestrator refactoring.

Verifies that:
- TaskContext is runtime_checkable and can be satisfied by a simple class
- orchestrate_pipeline accepts TaskContext (not AgentConsoleApp)
- log_decision accepts asyncpg.Pool (not aiosqlite.Connection)
"""
import inspect

import asyncpg

from src.pipeline.protocol import TaskContext
from src.pipeline.orchestrator import orchestrate_pipeline, log_decision


class MockTaskContext:
    """Simple class implementing all TaskContext methods for testing."""

    @property
    def project_path(self) -> str:
        return "/tmp/test"

    async def update_status(self, agent: str, state: str, step: str, next_action: str) -> None:
        pass

    async def stream_output(self, agent_name: str, prompt: str, sections: dict) -> dict[str, str]:
        return {}

    async def confirm_reroute(self, next_agent: str, reasoning: str) -> bool:
        return True

    async def handle_halt(self, iteration_count: int) -> str:
        return "continue"


def test_taskcontext_protocol():
    """A simple class implementing all TaskContext methods satisfies isinstance check."""
    ctx = MockTaskContext()
    assert isinstance(ctx, TaskContext)


def test_orchestrator_uses_protocol():
    """orchestrate_pipeline signature accepts TaskContext (not AgentConsoleApp) and asyncpg.Pool."""
    sig = inspect.signature(orchestrate_pipeline)
    params = sig.parameters

    # First parameter should be ctx (TaskContext), not app (AgentConsoleApp)
    param_names = list(params.keys())
    assert "ctx" in param_names, f"Expected 'ctx' parameter, got {param_names}"
    assert "app" not in param_names, "Should not have 'app' parameter (AgentConsoleApp)"

    # Should accept pool (asyncpg.Pool), not db (aiosqlite.Connection)
    assert "pool" in param_names, f"Expected 'pool' parameter, got {param_names}"
    assert "db" not in param_names, "Should not have 'db' parameter (aiosqlite.Connection)"


def test_log_decision_uses_pool():
    """log_decision accepts asyncpg.Pool (not aiosqlite.Connection)."""
    sig = inspect.signature(log_decision)
    params = sig.parameters

    param_names = list(params.keys())
    assert "pool" in param_names, f"Expected 'pool' parameter, got {param_names}"
    assert "db" not in param_names, "Should not have 'db' parameter (aiosqlite.Connection)"
