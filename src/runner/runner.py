"""
Claude CLI async subprocess runner.
Deadlock-safe: drains stdout before calling wait().
"""
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from collections.abc import AsyncGenerator

log = logging.getLogger(__name__)

# Windows: ProactorEventLoop is default on 3.10+, but guard explicitly.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

_CLAUDE_BIN: str | None = None


def _resolve_claude() -> str:
    global _CLAUDE_BIN
    if _CLAUDE_BIN is None:
        resolved = shutil.which("claude")
        if resolved is None:
            raise FileNotFoundError(
                "claude CLI not found on PATH. Install via: npm install -g @anthropic-ai/claude-code"
            )
        _CLAUDE_BIN = resolved
    return _CLAUDE_BIN


async def stream_claude(
    prompt: str,
    *,
    system_prompt_file: str | None = None,
    extra_args: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Async generator that launches Claude CLI and yields text chunks.

    Each yielded string is the extracted text from an assistant message.
    Non-JSON lines and non-assistant message types are silently skipped.
    Deadlock-safe: stdout is drained with async-for before wait() is called.
    """
    claude = _resolve_claude()
    cmd = [
        claude, "-p",
        "--verbose",
        "--output-format", "stream-json",
        "--dangerously-skip-permissions",
    ]
    if system_prompt_file:
        cmd += ["--system-prompt-file", system_prompt_file]
    if extra_args:
        cmd += extra_args
    cmd.append(prompt)

    # Remove CLAUDECODE env var to allow nested Claude CLI calls
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    # Drain stderr concurrently -- never block on it
    stderr_task = asyncio.create_task(proc.stderr.read())
    got_deltas = False

    async for raw_line in proc.stdout:
        line = raw_line.decode().strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            log.warning("non-JSON line from claude: %s", line[:120])
            continue

        msg_type = data.get("type")

        # Incremental text deltas — real-time streaming
        if msg_type == "content_block_delta":
            delta = data.get("delta", {})
            if delta.get("type") == "text_delta" and delta.get("text"):
                got_deltas = True
                yield delta["text"]

        # Final assistant message — fallback only if no deltas were received
        elif msg_type == "assistant" and not got_deltas:
            for block in data.get("message", {}).get("content", []):
                if block.get("type") == "text" and block.get("text"):
                    yield block["text"]

    await proc.wait()
    stderr = await stderr_task

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode,
            "claude",
            stderr=stderr.decode(errors="replace"),
        )


async def call_orchestrator_claude(prompt: str, schema: str) -> str:
    """
    Call Claude CLI with --output-format json --json-schema for structured output.

    Unlike stream_claude, this returns a single JSON response (not streamed).
    Uses a dedicated subprocess call rather than the streaming path.
    """
    claude = _resolve_claude()
    cmd = [
        claude, "-p",
        "--output-format", "json",
        "--json-schema", schema,
        "--dangerously-skip-permissions",
        prompt,
    ]

    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode,
            "claude",
            stderr=stderr.decode(errors="replace"),
        )

    return stdout.decode()


async def collect_claude(prompt: str, **kwargs) -> str:
    """Collect all text chunks from stream_claude into a single string."""
    chunks = []
    async for chunk in stream_claude(prompt, **kwargs):
        chunks.append(chunk)
    return "".join(chunks)
