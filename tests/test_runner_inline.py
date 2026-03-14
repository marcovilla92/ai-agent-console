"""Tests for inline system prompt support in runner functions."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.runner.runner import call_orchestrator_claude, stream_claude


class TestStreamClaudeInlineSystemPrompt:
    """stream_claude supports --system-prompt flag for inline prompts."""

    @pytest.mark.asyncio
    async def test_inline_system_prompt_flag(self):
        """system_prompt kwarg adds --system-prompt flag to subprocess cmd."""
        captured_cmd = []

        async def fake_exec(*cmd, **kwargs):
            captured_cmd.extend(cmd)
            proc = AsyncMock()
            proc.pid = 12345
            proc.returncode = 0
            # stdout yields no lines (empty async iterator)
            proc.stdout.__aiter__ = lambda self: self
            proc.stdout.__anext__ = AsyncMock(side_effect=StopAsyncIteration)
            proc.stderr = AsyncMock()
            proc.stderr.read = AsyncMock(return_value=b"")
            proc.wait = AsyncMock(return_value=0)
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            chunks = []
            async for chunk in stream_claude("test prompt", system_prompt="You are a DB expert"):
                chunks.append(chunk)

        assert "--system-prompt" in captured_cmd
        idx = captured_cmd.index("--system-prompt")
        assert captured_cmd[idx + 1] == "You are a DB expert"
        # Must NOT have --system-prompt-file
        assert "--system-prompt-file" not in captured_cmd

    @pytest.mark.asyncio
    async def test_inline_wins_over_file(self):
        """When both system_prompt and system_prompt_file given, inline wins."""
        captured_cmd = []

        async def fake_exec(*cmd, **kwargs):
            captured_cmd.extend(cmd)
            proc = AsyncMock()
            proc.pid = 12345
            proc.returncode = 0
            proc.stdout.__aiter__ = lambda self: self
            proc.stdout.__anext__ = AsyncMock(side_effect=StopAsyncIteration)
            proc.stderr = AsyncMock()
            proc.stderr.read = AsyncMock(return_value=b"")
            proc.wait = AsyncMock(return_value=0)
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            async for _ in stream_claude(
                "test prompt",
                system_prompt="Inline prompt",
                system_prompt_file="/path/to/file.txt",
            ):
                pass

        assert "--system-prompt" in captured_cmd
        idx = captured_cmd.index("--system-prompt")
        assert captured_cmd[idx + 1] == "Inline prompt"
        assert "--system-prompt-file" not in captured_cmd

    @pytest.mark.asyncio
    async def test_neither_prompt_omits_both_flags(self):
        """With no system_prompt or system_prompt_file, neither flag present."""
        captured_cmd = []

        async def fake_exec(*cmd, **kwargs):
            captured_cmd.extend(cmd)
            proc = AsyncMock()
            proc.pid = 12345
            proc.returncode = 0
            proc.stdout.__aiter__ = lambda self: self
            proc.stdout.__anext__ = AsyncMock(side_effect=StopAsyncIteration)
            proc.stderr = AsyncMock()
            proc.stderr.read = AsyncMock(return_value=b"")
            proc.wait = AsyncMock(return_value=0)
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            async for _ in stream_claude("test prompt"):
                pass

        assert "--system-prompt" not in captured_cmd
        assert "--system-prompt-file" not in captured_cmd


class TestCallOrchestratorClaudeInlineSystemPrompt:
    """call_orchestrator_claude supports --system-prompt flag."""

    @pytest.mark.asyncio
    async def test_inline_system_prompt_flag(self):
        """system_prompt kwarg adds --system-prompt flag."""
        captured_cmd = []

        async def fake_exec(*cmd, **kwargs):
            captured_cmd.extend(cmd)
            proc = AsyncMock()
            proc.pid = 12345
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b'{"result":"ok"}', b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            await call_orchestrator_claude(
                "test prompt",
                '{"type":"object"}',
                system_prompt="Dynamic prompt",
            )

        assert "--system-prompt" in captured_cmd
        idx = captured_cmd.index("--system-prompt")
        assert captured_cmd[idx + 1] == "Dynamic prompt"
        assert "--system-prompt-file" not in captured_cmd

    @pytest.mark.asyncio
    async def test_file_prompt_still_works(self):
        """system_prompt_file (existing behavior) still works when no inline."""
        captured_cmd = []

        async def fake_exec(*cmd, **kwargs):
            captured_cmd.extend(cmd)
            proc = AsyncMock()
            proc.pid = 12345
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b'{"result":"ok"}', b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            await call_orchestrator_claude(
                "test prompt",
                '{"type":"object"}',
                system_prompt_file="/path/to/prompt.txt",
            )

        assert "--system-prompt-file" in captured_cmd
        idx = captured_cmd.index("--system-prompt-file")
        assert captured_cmd[idx + 1] == "/path/to/prompt.txt"
        assert "--system-prompt" not in captured_cmd
