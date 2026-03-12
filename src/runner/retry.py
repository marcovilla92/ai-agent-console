"""
Tenacity-wrapped async Claude CLI invocation.

Retries on CalledProcessError or OSError with exponential backoff.
3 attempts max, reraises on exhaustion.
"""
import subprocess
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception_type,
)
from src.runner.runner import collect_claude


@retry(
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=1, max=10),
    retry=retry_if_exception_type((subprocess.CalledProcessError, OSError)),
    reraise=True,
)
async def invoke_claude_with_retry(prompt: str, **kwargs) -> str:
    """
    Invoke Claude CLI with automatic retry on transient failures.

    3 attempts with random exponential backoff (1-10 seconds between attempts).
    CalledProcessError and OSError trigger retry; all other exceptions propagate.
    After 3 failures, the final exception is re-raised (not swallowed).
    """
    return await collect_claude(prompt, **kwargs)
