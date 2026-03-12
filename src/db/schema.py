"""
Database schema: dataclasses and SQL definitions.

Single source of truth for table structure.
Uses stdlib dataclasses -- no ORM.
"""
from dataclasses import dataclass
from typing import Optional

# --- SQL -----------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    project_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    agent_type TEXT NOT NULL,
    raw_output TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    agent_type TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orchestrator_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    next_agent TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    confidence REAL,
    full_response TEXT NOT NULL,
    iteration_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""

# --- Dataclasses ---------------------------------------------------------


@dataclass
class Session:
    name: str
    project_path: str
    created_at: str
    id: Optional[int] = None


@dataclass
class AgentOutput:
    session_id: int
    agent_type: str       # 'plan' | 'execute' | 'review'
    raw_output: str
    created_at: str
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
    created_at: str
    id: Optional[int] = None


@dataclass
class OrchestratorDecisionRecord:
    session_id: int
    next_agent: str
    reasoning: str
    confidence: float
    full_response: str
    iteration_count: int
    created_at: str
    id: Optional[int] = None
