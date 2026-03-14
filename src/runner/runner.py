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
    system_prompt: str | None = None,
    system_prompt_file: str | None = None,
    extra_args: list[str] | None = None,
    on_process: callable = None,
) -> AsyncGenerator[str | dict, None]:
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
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]
    elif system_prompt_file:
        cmd += ["--system-prompt-file", system_prompt_file]
    if extra_args:
        cmd += extra_args
    cmd.append(prompt)

    log.info("stream_claude: launching cmd=%s", " ".join(cmd[:6]) + "...")
    log.info("stream_claude: system_prompt_file=%s", system_prompt_file)
    log.info("stream_claude: prompt_len=%d prompt_preview=%r", len(prompt), prompt[:200])

    # Remove CLAUDECODE env var to allow nested Claude CLI calls
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        limit=10 * 1024 * 1024,  # 10 MB line buffer (default 64KB too small for large JSON lines)
    )
    log.info("stream_claude: process started pid=%s", proc.pid)

    # Expose process reference for termination support
    if on_process is not None:
        on_process(proc)

    # Drain stderr concurrently -- never block on it
    stderr_task = asyncio.create_task(proc.stderr.read())
    got_deltas = False
    chunk_count = 0
    total_chars = 0

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
                chunk_count += 1
                total_chars += len(delta["text"])
                if chunk_count <= 3 or chunk_count % 50 == 0:
                    log.debug("stream_claude: delta #%d chars_so_far=%d preview=%r", chunk_count, total_chars, delta["text"][:80])
                yield delta["text"]

        # Final assistant message — fallback only if no deltas were received
        elif msg_type == "assistant" and not got_deltas:
            log.info("stream_claude: got assistant message (fallback mode)")
            for block in data.get("message", {}).get("content", []):
                if block.get("type") == "text" and block.get("text"):
                    yield block["text"]

        # Result event — yield as dict with usage/cost metadata
        elif msg_type == "result":
            usage = data.get("usage", {})
            result_data = {
                "type": "result",
                "cost_usd": data.get("total_cost_usd", 0.0) or data.get("cost_usd", 0.0),
                "num_turns": data.get("num_turns", 0),
                "session_id": data.get("session_id", ""),
                "input_tokens": usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0) + usage.get("cache_creation_input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
                "cache_creation_tokens": usage.get("cache_creation_input_tokens", 0),
            }
            log.info("stream_claude: result event cost=$%.4f input_tok=%d output_tok=%d chunks=%d chars=%d",
                     result_data["cost_usd"], result_data["input_tokens"],
                     result_data["output_tokens"], chunk_count, total_chars)
            yield result_data
        else:
            log.debug("stream_claude: skipped event type=%s", msg_type)

    await proc.wait()
    stderr = await stderr_task
    log.info("stream_claude: process exited rc=%s total_chunks=%d total_chars=%d", proc.returncode, chunk_count, total_chars)

    if proc.returncode != 0:
        stderr_text = stderr.decode(errors="replace")
        log.error("stream_claude: FAILED rc=%s stderr=%s", proc.returncode, stderr_text[:500])
        raise subprocess.CalledProcessError(
            proc.returncode,
            "claude",
            stderr=stderr_text,
        )


async def call_orchestrator_claude(prompt: str, schema: str, system_prompt_file: str | None = None, system_prompt: str | None = None) -> str:
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
    ]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]
    elif system_prompt_file:
        cmd += ["--system-prompt-file", system_prompt_file]
    cmd.append(prompt)

    log.info("call_orchestrator_claude: launching decision call, prompt_len=%d system_prompt_file=%s", len(prompt), system_prompt_file)
    log.debug("call_orchestrator_claude: prompt_preview=%r", prompt[:300])

    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    log.info("call_orchestrator_claude: process started pid=%s", proc.pid)
    stdout, stderr = await proc.communicate()
    log.info("call_orchestrator_claude: process exited rc=%s stdout_len=%d", proc.returncode, len(stdout))

    if proc.returncode != 0:
        stderr_text = stderr.decode(errors="replace")
        log.error("call_orchestrator_claude: FAILED stderr=%s", stderr_text[:500])
        raise subprocess.CalledProcessError(
            proc.returncode,
            "claude",
            stderr=stderr_text,
        )

    result = stdout.decode()
    log.info("call_orchestrator_claude: response=%r", result[:500])
    return result


async def collect_claude(prompt: str, **kwargs) -> str:
    """Collect all text chunks from stream_claude into a single string."""
    chunks = []
    async for chunk in stream_claude(prompt, **kwargs):
        chunks.append(chunk)
    return "".join(chunks)
