"""
Repository classes for Session and AgentOutput persistence.

Both classes accept an aiosqlite.Connection injected at construction.
Use a single shared connection for the app lifetime to avoid lock contention.
"""
import aiosqlite
from typing import Optional

from src.db.schema import Session, AgentOutput, AgentUsage, OrchestratorDecisionRecord


class SessionRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, session: Session) -> int:
        cursor = await self._db.execute(
            "INSERT INTO sessions (name, project_path, created_at) VALUES (?, ?, ?)",
            (session.name, session.project_path, session.created_at),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get(self, session_id: int) -> Optional[Session]:
        async with self._db.execute(
            "SELECT id, name, project_path, created_at FROM sessions WHERE id = ?",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return Session(id=row[0], name=row[1], project_path=row[2], created_at=row[3])

    async def list_all(self) -> list[Session]:
        async with self._db.execute(
            "SELECT id, name, project_path, created_at FROM sessions ORDER BY id DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [Session(id=r[0], name=r[1], project_path=r[2], created_at=r[3]) for r in rows]


class AgentOutputRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, output: AgentOutput) -> int:
        cursor = await self._db.execute(
            "INSERT INTO agent_outputs (session_id, agent_type, raw_output, created_at) VALUES (?, ?, ?, ?)",
            (output.session_id, output.agent_type, output.raw_output, output.created_at),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_by_session(self, session_id: int) -> list[AgentOutput]:
        async with self._db.execute(
            "SELECT id, session_id, agent_type, raw_output, created_at FROM agent_outputs WHERE session_id = ? ORDER BY id",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                AgentOutput(id=r[0], session_id=r[1], agent_type=r[2], raw_output=r[3], created_at=r[4])
                for r in rows
            ]


class OrchestratorDecisionRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, record: OrchestratorDecisionRecord) -> int:
        cursor = await self._db.execute(
            "INSERT INTO orchestrator_decisions "
            "(session_id, next_agent, reasoning, confidence, full_response, iteration_count, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                record.session_id,
                record.next_agent,
                record.reasoning,
                record.confidence,
                record.full_response,
                record.iteration_count,
                record.created_at,
            ),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_by_session(self, session_id: int) -> list[OrchestratorDecisionRecord]:
        async with self._db.execute(
            "SELECT id, session_id, next_agent, reasoning, confidence, full_response, iteration_count, created_at "
            "FROM orchestrator_decisions WHERE session_id = ? ORDER BY id",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                OrchestratorDecisionRecord(
                    id=r[0], session_id=r[1], next_agent=r[2], reasoning=r[3],
                    confidence=r[4], full_response=r[5], iteration_count=r[6], created_at=r[7],
                )
                for r in rows
            ]


class UsageRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, usage: AgentUsage) -> int:
        cursor = await self._db.execute(
            "INSERT INTO agent_usage "
            "(session_id, agent_type, input_tokens, output_tokens, "
            "cache_read_tokens, cache_creation_tokens, cost_usd, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                usage.session_id,
                usage.agent_type,
                usage.input_tokens,
                usage.output_tokens,
                usage.cache_read_tokens,
                usage.cache_creation_tokens,
                usage.cost_usd,
                usage.created_at,
            ),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_by_session(self, session_id: int) -> list[AgentUsage]:
        async with self._db.execute(
            "SELECT id, session_id, agent_type, input_tokens, output_tokens, "
            "cache_read_tokens, cache_creation_tokens, cost_usd, created_at "
            "FROM agent_usage WHERE session_id = ? ORDER BY id",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                AgentUsage(
                    id=r[0], session_id=r[1], agent_type=r[2],
                    input_tokens=r[3], output_tokens=r[4],
                    cache_read_tokens=r[5], cache_creation_tokens=r[6],
                    cost_usd=r[7], created_at=r[8],
                )
                for r in rows
            ]
