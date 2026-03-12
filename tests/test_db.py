from src.db.schema import Session, AgentOutput
from src.db.repository import SessionRepository, AgentOutputRepository


async def test_session_create(db_conn):
    """INFR-03: session saved and returns auto-increment id >= 1."""
    repo = SessionRepository(db_conn)
    session = Session(name="test session", project_path="/tmp/proj", created_at="2026-01-01T00:00:00")
    session_id = await repo.create(session)
    assert isinstance(session_id, int)
    assert session_id >= 1


async def test_session_get(db_conn):
    """INFR-03: saved session retrieved with correct fields."""
    repo = SessionRepository(db_conn)
    session = Session(name="my project", project_path="/home/user/proj", created_at="2026-01-01T12:00:00")
    session_id = await repo.create(session)

    fetched = await repo.get(session_id)
    assert fetched is not None
    assert fetched.name == "my project"
    assert fetched.project_path == "/home/user/proj"
    assert fetched.id == session_id


async def test_session_get_missing(db_conn):
    """INFR-03: get() returns None for non-existent id."""
    repo = SessionRepository(db_conn)
    result = await repo.get(99999)
    assert result is None


async def test_agent_output_persistence(db_conn):
    """INFR-03: agent_output saved and linked to session_id."""
    session_repo = SessionRepository(db_conn)
    output_repo = AgentOutputRepository(db_conn)

    session_id = await session_repo.create(
        Session(name="s", project_path="/tmp", created_at="2026-01-01T00:00:00")
    )
    output = AgentOutput(
        session_id=session_id,
        agent_type="plan",
        raw_output="GOAL:\nBuild it",
        created_at="2026-01-01T00:01:00",
    )
    output_id = await output_repo.create(output)
    assert output_id >= 1

    outputs = await output_repo.get_by_session(session_id)
    assert len(outputs) == 1
    assert outputs[0].agent_type == "plan"
    assert outputs[0].raw_output == "GOAL:\nBuild it"
    assert outputs[0].session_id == session_id
