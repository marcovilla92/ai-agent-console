"""
Agent factory.

Creates agent instances from the registry. All agents currently use
BaseAgent -- subclasses exist only if agent-specific logic is needed.
"""
import aiosqlite

from src.agents.base import BaseAgent
from src.agents.config import get_agent_config


def create_agent(name: str, db: aiosqlite.Connection, project_path: str) -> BaseAgent:
    """Create an agent instance by name from the registry."""
    config = get_agent_config(name)
    return BaseAgent(config, db, project_path)
