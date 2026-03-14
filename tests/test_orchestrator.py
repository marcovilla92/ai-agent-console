"""
Tests for the orchestrator core: state management, decision parsing,
prompt building, DB logging, and the orchestration loop.
"""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.pipeline.orchestrator import (
    ORCHESTRATOR_SCHEMA,
    OrchestratorDecision,
    OrchestratorState,
    build_orchestrator_prompt,
    build_orchestrator_schema,
    build_orchestrator_system_prompt,
    get_orchestrator_decision,
    log_decision,
    orchestrate_pipeline,
    parse_decision_from_text,
)
from src.db.repository import OrchestratorDecisionRepository
from src.db.schema import OrchestratorDecisionRecord


# --- OrchestratorState defaults ---

class TestOrchestratorState:
    def test_defaults(self):
        state = OrchestratorState(session_id=1, original_prompt="build a web app")
        assert state.iteration_count == 0
        assert state.max_iterations == 3
        assert state.current_agent == "plan"
        assert state.halted is False
        assert state.approved is False
        assert state.history == []
        assert state.decisions == []
        assert state.accumulated_handoffs == []


# --- OrchestratorDecision ---

class TestOrchestratorDecision:
    def test_stores_fields(self):
        d = OrchestratorDecision(
            next_agent="execute",
            reasoning="Plan looks complete",
            confidence=0.9,
            full_response='{"next_agent":"execute"}',
        )
        assert d.next_agent == "execute"
        assert d.reasoning == "Plan looks complete"
        assert d.confidence == 0.9
        assert d.full_response == '{"next_agent":"execute"}'
        assert d.timestamp  # auto-generated, not empty


# --- build_orchestrator_prompt ---

class TestBuildOrchestratorPrompt:
    def test_includes_current_agent(self):
        state = OrchestratorState(session_id=1, original_prompt="test")
        state.current_agent = "review"
        prompt = build_orchestrator_prompt(state, {"DECISION": "APPROVED"})
        assert "REVIEW" in prompt

    def test_includes_iteration_count(self):
        state = OrchestratorState(session_id=1, original_prompt="test")
        state.iteration_count = 2
        prompt = build_orchestrator_prompt(state, {})
        assert "2" in prompt

    def test_includes_workflow_history(self):
        state = OrchestratorState(session_id=1, original_prompt="test")
        state.history = [
            {"agent": "plan", "sections_keys": ["PLAN"]},
            {"agent": "execute", "sections_keys": ["CODE"]},
        ]
        prompt = build_orchestrator_prompt(state, {})
        assert "PLAN" in prompt and "EXECUTE" in prompt

    def test_truncates_long_sections(self):
        state = OrchestratorState(session_id=1, original_prompt="test")
        state.current_agent = "review"  # review allows SUMMARY section
        long_content = "x" * 1000
        prompt = build_orchestrator_prompt(state, {"SUMMARY": long_content})
        # Should be truncated to 500 chars + "..."
        assert "x" * 500 in prompt
        assert "..." in prompt
        assert "x" * 501 not in prompt


# --- get_orchestrator_decision ---

class TestGetOrchestratorDecision:
    @pytest.mark.asyncio
    async def test_parses_valid_json(self):
        json_response = json.dumps({
            "result": json.dumps({
                "next_agent": "execute",
                "reasoning": "Plan complete, proceed to execution",
                "confidence": 0.95,
            })
        })
        with patch(
            "src.pipeline.orchestrator.call_orchestrator_claude",
            new_callable=AsyncMock,
            return_value=json_response,
        ):
            state = OrchestratorState(session_id=1, original_prompt="test")
            decision = await get_orchestrator_decision(state, {"PLAN": "some plan"})
            assert decision.next_agent == "execute"
            assert decision.confidence == 0.95
            assert decision.reasoning == "Plan complete, proceed to execution"

    @pytest.mark.asyncio
    async def test_fallback_approved(self):
        with patch(
            "src.pipeline.orchestrator.call_orchestrator_claude",
            new_callable=AsyncMock,
            return_value="The review says APPROVED, everything looks good.",
        ):
            state = OrchestratorState(session_id=1, original_prompt="test")
            decision = await get_orchestrator_decision(state, {"DECISION": "APPROVED"})
            assert decision.next_agent == "approved"
            assert decision.confidence == 0.3

    @pytest.mark.asyncio
    async def test_fallback_back_to_plan(self):
        with patch(
            "src.pipeline.orchestrator.call_orchestrator_claude",
            new_callable=AsyncMock,
            return_value="Issues found, recommending BACK TO PLAN",
        ):
            state = OrchestratorState(session_id=1, original_prompt="test")
            decision = await get_orchestrator_decision(state, {})
            assert decision.next_agent == "plan"
            assert decision.confidence == 0.3

    @pytest.mark.asyncio
    async def test_fallback_back_to_execute(self):
        with patch(
            "src.pipeline.orchestrator.call_orchestrator_claude",
            new_callable=AsyncMock,
            return_value="Minor code issues, BACK TO EXECUTE",
        ):
            state = OrchestratorState(session_id=1, original_prompt="test")
            decision = await get_orchestrator_decision(state, {})
            assert decision.next_agent == "execute"
            assert decision.confidence == 0.3


# --- parse_decision_from_text ---

class TestParseDecisionFromText:
    def test_approved(self):
        d = parse_decision_from_text("The output is APPROVED for release")
        assert d.next_agent == "approved"
        assert d.confidence == 0.3

    def test_back_to_plan(self):
        d = parse_decision_from_text("Need to go BACK TO PLAN")
        assert d.next_agent == "plan"

    def test_back_to_execute(self):
        d = parse_decision_from_text("Issues in code, BACK TO EXECUTE")
        assert d.next_agent == "execute"

    def test_unknown_defaults_to_review(self):
        d = parse_decision_from_text("Some random text with no clear decision")
        assert d.next_agent == "review"


# --- OrchestratorDecisionRepository ---

class TestOrchestratorDecisionRepository:
    @pytest.mark.asyncio
    async def test_create_returns_id(self, db_conn):
        now = datetime.now(timezone.utc).isoformat()
        # Insert a session first (FK constraint)
        await db_conn.execute(
            "INSERT INTO sessions (name, project_path, created_at) VALUES (?, ?, ?)",
            ("test", "/tmp", now),
        )
        await db_conn.commit()

        repo = OrchestratorDecisionRepository(db_conn)
        record = OrchestratorDecisionRecord(
            session_id=1,
            next_agent="execute",
            reasoning="test",
            confidence=0.9,
            full_response="{}",
            iteration_count=0,
            created_at=now,
        )
        row_id = await repo.create(record)
        assert isinstance(row_id, int)
        assert row_id > 0

    @pytest.mark.asyncio
    async def test_get_by_session_ordered(self, db_conn):
        repo = OrchestratorDecisionRepository(db_conn)
        now = datetime.now(timezone.utc).isoformat()

        # Insert a session first (FK constraint)
        await db_conn.execute(
            "INSERT INTO sessions (name, project_path, created_at) VALUES (?, ?, ?)",
            ("test", "/tmp", now),
        )
        await db_conn.commit()

        for agent in ["execute", "review", "plan"]:
            await repo.create(OrchestratorDecisionRecord(
                session_id=1,
                next_agent=agent,
                reasoning=f"go to {agent}",
                confidence=0.8,
                full_response="{}",
                iteration_count=0,
                created_at=now,
            ))

        decisions = await repo.get_by_session(1)
        assert len(decisions) == 3
        assert decisions[0].next_agent == "execute"
        assert decisions[1].next_agent == "review"
        assert decisions[2].next_agent == "plan"


# --- log_decision ---

class TestLogDecision:
    @pytest.mark.asyncio
    async def test_persists_to_db(self, db_conn):
        # Insert a session first (FK constraint)
        now = datetime.now(timezone.utc).isoformat()
        await db_conn.execute(
            "INSERT INTO sessions (name, project_path, created_at) VALUES (?, ?, ?)",
            ("test", "/tmp", now),
        )
        await db_conn.commit()

        decision = OrchestratorDecision(
            next_agent="execute",
            reasoning="plan complete",
            confidence=0.9,
            full_response='{"next_agent":"execute"}',
        )
        await log_decision(db_conn, session_id=1, decision=decision, iteration_count=0)

        repo = OrchestratorDecisionRepository(db_conn)
        rows = await repo.get_by_session(1)
        assert len(rows) == 1
        assert rows[0].next_agent == "execute"
        assert rows[0].reasoning == "plan complete"


# --- Phase 28: Dynamic schema and system prompt builders ---


class TestDynamicSchemaBuilder:
    """build_orchestrator_schema(registry) produces correct JSON schemas."""

    def test_with_project_agent_includes_name(self):
        """Registry with a project agent 'db-migrator' appears in enum."""
        from src.agents.config import AgentConfig, DEFAULT_REGISTRY

        custom_reg = dict(DEFAULT_REGISTRY)
        custom_reg["db-migrator"] = AgentConfig(
            name="db-migrator",
            system_prompt_file="",
            description="Handles database migrations",
            source="project",
        )
        schema_json = build_orchestrator_schema(custom_reg)
        schema = json.loads(schema_json)
        enum_values = schema["properties"]["next_agent"]["enum"]
        assert "db-migrator" in enum_values

    def test_default_registry_matches_constant(self):
        """build_orchestrator_schema() with no args matches ORCHESTRATOR_SCHEMA."""
        from src.agents.config import DEFAULT_REGISTRY

        fresh = build_orchestrator_schema(DEFAULT_REGISTRY)
        assert json.loads(fresh) == json.loads(ORCHESTRATOR_SCHEMA)


class TestDynamicSystemPromptBuilder:
    """build_orchestrator_system_prompt(registry) returns correct prompts."""

    def test_default_registry_returns_base_text(self):
        """Default registry (no project agents) returns base prompt unchanged."""
        from src.agents.config import DEFAULT_REGISTRY

        result = build_orchestrator_system_prompt(DEFAULT_REGISTRY)
        assert "workflow orchestrator" in result.lower()
        # No project agents section
        assert "Project-specific specialist agents:" not in result

    def test_project_agent_appended(self):
        """Registry with project agent appends description section."""
        from src.agents.config import AgentConfig, DEFAULT_REGISTRY

        custom_reg = dict(DEFAULT_REGISTRY)
        custom_reg["db-migrator"] = AgentConfig(
            name="db-migrator",
            system_prompt_file="",
            description="Handles database migrations",
            source="project",
        )
        result = build_orchestrator_system_prompt(custom_reg)
        assert "Project-specific specialist agents:" in result
        assert "DB-MIGRATOR" in result
        assert "Handles database migrations" in result
