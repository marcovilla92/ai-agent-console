"""
PostgreSQL schema: dataclasses and DDL definitions for v2.0 web platform.

Uses PostgreSQL-native types (SERIAL, TIMESTAMPTZ, DOUBLE PRECISION).
Separate from schema.py which remains for v1.0 TUI/aiosqlite mode.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# --- SQL -----------------------------------------------------------------

PG_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    project_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_outputs (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES tasks(id),
    agent_type TEXT NOT NULL,
    raw_output TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_usage (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES tasks(id),
    agent_type TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orchestrator_decisions (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES tasks(id),
    next_agent TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    confidence DOUBLE PRECISION,
    full_response TEXT NOT NULL,
    iteration_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

# --- Dataclasses ---------------------------------------------------------


@dataclass
class Task:
    """A task (formerly Session in v1.0). Represents a single orchestration run."""
    name: str
    project_path: str
    created_at: datetime
    id: Optional[int] = None


@dataclass
class AgentOutput:
    session_id: int
    agent_type: str       # 'plan' | 'execute' | 'review'
    raw_output: str
    created_at: datetime
    id: Optional[int] = None


@dataclass
class AgentUsage:
    session_id: int
    agent_type: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    cost_usd: float
    created_at: datetime
    id: Optional[int] = None


@dataclass
class OrchestratorDecisionRecord:
    session_id: int
    next_agent: str
    reasoning: str
    confidence: float
    full_response: str
    iteration_count: int
    created_at: datetime
    id: Optional[int] = None
