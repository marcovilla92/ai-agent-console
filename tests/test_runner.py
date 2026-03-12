import pytest
import subprocess
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


@pytest.mark.skip(reason="retry wrapper tested in plan 03 (test_runner.py retry tests)")
async def test_retry_behavior():
    pass


@pytest.mark.skip(reason="retry wrapper tested in plan 03 (test_runner.py retry tests)")
async def test_retry_exhausted():
    pass
