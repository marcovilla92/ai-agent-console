"""
Tests for FIX-01 (stream_output system prompt) and FIX-02 (orchestrator system prompt).

Verifies that:
- stream_output passes system_prompt_file from agent config to stream_claude
- Unknown agent names fall back gracefully (no crash)
- call_orchestrator_claude builds --system-prompt-file flag when provided
- call_orchestrator_claude omits flag when not provided
- get_orchestrator_decision passes ORCHESTRATOR_PROMPT_FILE to call_orchestrator_claude
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.config import AgentConfig


# ---------------------------------------------------------------------------
# Test 1 & 2: stream_output wires system_prompt_file via get_agent_config
# ---------------------------------------------------------------------------

class TestStreamOutputSystemPrompt:
    """FIX-01: stream_output must look up agent config and pass system_prompt_file."""

    @pytest.mark.asyncio
    async def test_known_agent_passes_system_prompt(self):
        """stream_output should pass system_prompt_file from agent config to stream_claude."""
        fake_config = AgentConfig(
            name="plan",
            system_prompt_file="/path/to/plan_system.txt",
        )

        async def fake_stream(prompt, *, system_prompt_file=None, extra_args=None):
            yield "chunk"

        mock_pool = MagicMock()

        with patch("src.engine.context.get_agent_config", return_value=fake_config) as mock_get, \
             patch("src.engine.context.stream_claude", side_effect=fake_stream) as mock_stream:
            from src.engine.context import WebTaskContext

            ctx = WebTaskContext(task_id=1, pool=mock_pool, mode="autonomous")
            # Patch out DB persistence
            with patch("src.engine.context.AgentOutputRepository"):
                result = await ctx.stream_output("plan", "test prompt", {})

            mock_get.assert_called_once_with("plan")
            # Verify stream_claude was called with system_prompt_file
            mock_stream.assert_called_once()
            call_kwargs = mock_stream.call_args
            assert call_kwargs.kwargs.get("system_prompt_file") == "/path/to/plan_system.txt", \
                f"Expected system_prompt_file='/path/to/plan_system.txt', got {call_kwargs}"

    @pytest.mark.asyncio
    async def test_unknown_agent_falls_back_to_none(self):
        """stream_output with unknown agent_name should not crash, passes system_prompt_file=None."""

        async def fake_stream(prompt, *, system_prompt_file=None, extra_args=None):
            yield "chunk"

        mock_pool = MagicMock()

        with patch("src.engine.context.get_agent_config", side_effect=KeyError("unknown")), \
             patch("src.engine.context.stream_claude", side_effect=fake_stream) as mock_stream:
            from src.engine.context import WebTaskContext

            ctx = WebTaskContext(task_id=1, pool=mock_pool, mode="autonomous")
            with patch("src.engine.context.AgentOutputRepository"):
                result = await ctx.stream_output("unknown_agent", "test prompt", {})

            mock_stream.assert_called_once()
            call_kwargs = mock_stream.call_args
            assert call_kwargs.kwargs.get("system_prompt_file") is None, \
                "Unknown agent should fall back to system_prompt_file=None"


# ---------------------------------------------------------------------------
# Test 3 & 4: call_orchestrator_claude builds --system-prompt-file flag
# ---------------------------------------------------------------------------

class TestCallOrchestratorSystemPrompt:
    """FIX-02: call_orchestrator_claude must accept and use system_prompt_file."""

    @pytest.mark.asyncio
    async def test_builds_system_prompt_flag_when_provided(self):
        """call_orchestrator_claude should add --system-prompt-file to cmd when provided."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            json.dumps({"result": "ok"}).encode(),
            b"",
        )
        mock_proc.returncode = 0

        with patch("src.runner.runner._resolve_claude", return_value="/usr/bin/claude"), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            from src.runner.runner import call_orchestrator_claude

            await call_orchestrator_claude("prompt", "schema", system_prompt_file="/path/to/orch.txt")

            # Get the cmd args passed to create_subprocess_exec
            call_args = mock_exec.call_args[0]  # positional args
            assert "--system-prompt-file" in call_args, \
                f"Expected --system-prompt-file in cmd, got {call_args}"
            idx = list(call_args).index("--system-prompt-file")
            assert call_args[idx + 1] == "/path/to/orch.txt"

    @pytest.mark.asyncio
    async def test_omits_system_prompt_flag_when_none(self):
        """call_orchestrator_claude should NOT add --system-prompt-file when not provided."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            json.dumps({"result": "ok"}).encode(),
            b"",
        )
        mock_proc.returncode = 0

        with patch("src.runner.runner._resolve_claude", return_value="/usr/bin/claude"), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            from src.runner.runner import call_orchestrator_claude

            await call_orchestrator_claude("prompt", "schema")

            call_args = mock_exec.call_args[0]
            assert "--system-prompt-file" not in call_args, \
                f"Expected no --system-prompt-file in cmd, got {call_args}"


# ---------------------------------------------------------------------------
# Test 5: get_orchestrator_decision passes ORCHESTRATOR_PROMPT_FILE
# ---------------------------------------------------------------------------

class TestOrchestratorDecisionUsesPromptFile:
    """FIX-02: get_orchestrator_decision must pass ORCHESTRATOR_PROMPT_FILE."""

    @pytest.mark.asyncio
    async def test_passes_orchestrator_prompt_file(self):
        """get_orchestrator_decision should pass orchestrator_system.txt path."""
        from src.pipeline.orchestrator import OrchestratorState

        state = OrchestratorState(session_id=1, original_prompt="test")
        state.current_agent = "review"

        fake_response = json.dumps({
            "structured_output": {
                "next_agent": "approved",
                "reasoning": "looks good",
                "confidence": 0.9,
            }
        })

        with patch("src.pipeline.orchestrator.call_orchestrator_claude",
                    new_callable=AsyncMock, return_value=fake_response) as mock_call:
            from src.pipeline.orchestrator import get_orchestrator_decision

            decision = await get_orchestrator_decision(state, {"SUMMARY": "all good"})

            mock_call.assert_called_once()
            call_args = mock_call.call_args[0]
            assert len(call_args) == 3, \
                f"Expected 3 positional args (prompt, schema, prompt_file), got {len(call_args)}"
            assert call_args[2].endswith("orchestrator_system.txt"), \
                f"Expected path ending in orchestrator_system.txt, got {call_args[2]}"
