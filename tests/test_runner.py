import pytest
import subprocess
from unittest.mock import patch
from src.runner.runner import stream_claude, collect_claude


async def test_stream_lines_yielded(mock_claude_proc, monkeypatch):
    """INFR-01: runner yields text from assistant message blocks."""
    import src.runner.runner as runner_mod
    import asyncio

    # Patch create_subprocess_exec to return mock proc
    async def fake_exec(*args, **kwargs):
        return mock_claude_proc

    # Also need mock stderr
    class FakeStderr:
        async def read(self):
            return b""

    mock_claude_proc.stderr = FakeStderr()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(runner_mod, "_CLAUDE_BIN", "claude")

    result = []
    async for chunk in stream_claude("test prompt"):
        result.append(chunk)

    assert result == ["hello"]


async def test_stream_terminates(mock_claude_proc, monkeypatch):
    """INFR-01: generator completes (StopAsyncIteration) after all lines consumed."""
    import src.runner.runner as runner_mod
    import asyncio

    class FakeStderr:
        async def read(self):
            return b""

    mock_claude_proc.stderr = FakeStderr()

    async def fake_exec(*args, **kwargs):
        return mock_claude_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(runner_mod, "_CLAUDE_BIN", "claude")

    chunks = []
    async for chunk in stream_claude("test"):
        chunks.append(chunk)

    # Generator completed naturally -- no hang
    assert isinstance(chunks, list)


# --- Retry tests (INFR-05) ---


async def test_retry_behavior():
    """INFR-05: invoke_claude_with_retry retries on CalledProcessError, succeeds on 3rd attempt."""
    from src.runner.retry import invoke_claude_with_retry

    call_count = 0

    async def flaky_collect(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise subprocess.CalledProcessError(1, "claude")
        return "success output"

    with patch("src.runner.retry.collect_claude", side_effect=flaky_collect):
        result = await invoke_claude_with_retry("test prompt")

    assert result == "success output"
    assert call_count == 3


async def test_retry_exhausted():
    """INFR-05: after 3 failures CalledProcessError is re-raised (not swallowed)."""
    from src.runner.retry import invoke_claude_with_retry

    async def always_fail(prompt, **kwargs):
        raise subprocess.CalledProcessError(1, "claude", stderr="rate limited")

    with patch("src.runner.retry.collect_claude", side_effect=always_fail):
        with pytest.raises(subprocess.CalledProcessError):
            await invoke_claude_with_retry("test prompt")
