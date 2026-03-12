import pytest


@pytest.mark.skip(reason="stub -- implement in plan 02")
async def test_stream_lines_yielded():
    """INFR-01: runner yields decoded lines from subprocess stdout."""
    pass


@pytest.mark.skip(reason="stub -- implement in plan 02")
async def test_stream_terminates():
    """INFR-01: stream closes cleanly after subprocess exits."""
    pass


@pytest.mark.skip(reason="stub -- implement in plan 02")
async def test_retry_behavior():
    """INFR-05: invoke_claude retries up to 3 times on CalledProcessError."""
    pass


@pytest.mark.skip(reason="stub -- implement in plan 02")
async def test_retry_exhausted():
    """INFR-05: after 3 failures the error surfaces (is not swallowed)."""
    pass
