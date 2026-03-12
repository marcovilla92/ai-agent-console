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
