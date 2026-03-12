"""
Base agent class.

Handles the common lifecycle: build context -> invoke Claude CLI -> parse
sections -> persist output -> return structured result.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

import aiosqlite

from src.agents.config import AgentConfig
from src.context.assembler import assemble_workspace_context
from src.db.repository import AgentOutputRepository
from src.db.schema import AgentOutput
from src.parser.extractor import extract_sections
from src.runner.retry import invoke_claude_with_retry


@dataclass
class AgentResult:
    agent_name: str
    raw_output: str
    sections: dict[str, str] = field(default_factory=dict)
    handoff: str | None = None


class BaseAgent:
    def __init__(
        self,
        config: AgentConfig,
        db: aiosqlite.Connection,
        project_path: str,
    ) -> None:
        self.config = config
        self._db = db
        self._project_path = project_path
        self._repo = AgentOutputRepository(db)

    async def run(self, prompt: str, session_id: int) -> AgentResult:
        """
        Execute the agent: invoke Claude CLI with context, parse output,
        persist to DB, and return structured AgentResult.
        """
        full_prompt = self._build_prompt(prompt)

        raw_output = await invoke_claude_with_retry(
            full_prompt,
            system_prompt_file=self.config.system_prompt_file,
        )

        sections = extract_sections(raw_output)

        await self._repo.create(AgentOutput(
            session_id=session_id,
            agent_type=self.config.name,
            raw_output=raw_output,
            created_at=datetime.now(timezone.utc).isoformat(),
        ))

        handoff = sections.get("HANDOFF")

        return AgentResult(
            agent_name=self.config.name,
            raw_output=raw_output,
            sections=sections,
            handoff=handoff,
        )

    def _build_prompt(self, user_prompt: str) -> str:
        """Prepend workspace context to the user's prompt."""
        context = assemble_workspace_context(self._project_path)
        return f"{context}\n{user_prompt}"
