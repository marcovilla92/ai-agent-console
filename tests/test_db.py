import pytest


@pytest.mark.skip(reason="stub -- implement in plan 03")
async def test_session_create(db_conn):
    """INFR-03: session saved and returns auto-incremented id."""
    pass


@pytest.mark.skip(reason="stub -- implement in plan 03")
async def test_session_get(db_conn):
    """INFR-03: saved session retrieved by id with correct fields."""
    pass


@pytest.mark.skip(reason="stub -- implement in plan 03")
async def test_agent_output_persistence(db_conn):
    """INFR-03: agent_output saved and linked to session_id."""
    pass
