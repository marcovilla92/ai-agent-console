"""Shared test fixtures."""
import os

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def test_dsn():
    return os.environ.get("TEST_DATABASE_URL", "postgresql://user:pass@localhost:5432/test")
