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


# --- Phase 28-02: Registry threading through pipeline ---


class TestWebTaskContextRegistry:
    """WebTaskContext stores registry and uses it for agent resolution."""

    def test_init_accepts_registry(self):
        """WebTaskContext.__init__ accepts registry kwarg and stores it."""
        from src.engine.context import WebTaskContext
        from src.agents.config import AgentConfig

        reg = {"custom": AgentConfig(name="custom", system_prompt_file="", source="project")}
        ctx = WebTaskContext(task_id=1, pool=MagicMock(), mode="autonomous", registry=reg)
        assert ctx._registry is reg

    def test_init_default_registry_is_none(self):
        """WebTaskContext without registry kwarg defaults to None."""
        from src.engine.context import WebTaskContext

        ctx = WebTaskContext(task_id=1, pool=MagicMock(), mode="autonomous")
        assert ctx._registry is None

    @pytest.mark.asyncio
    async def test_stream_output_uses_registry_for_agent_resolution(self):
        """stream_output passes registry to get_agent_config."""
        from src.engine.context import WebTaskContext
        from src.agents.config import AgentConfig

        reg = {
            "db-migrator": AgentConfig(
                name="db-migrator",
                system_prompt_file="",
                system_prompt_inline="You are a DB migration specialist.",
                source="project",
            ),
        }
        ctx = WebTaskContext(task_id=1, pool=MagicMock(), mode="autonomous", registry=reg)

        with patch("src.engine.context.get_agent_config") as mock_get:
            mock_get.return_value = reg["db-migrator"]
            with patch("src.engine.context.stream_claude") as mock_stream:
                async def _fake_stream(*a, **kw):
                    yield "output text"
                mock_stream.return_value = _fake_stream()
                # Mock the DB persist
                with patch("src.engine.context.AgentOutputRepository"):
                    await ctx.stream_output("db-migrator", "migrate the DB", {})

            mock_get.assert_called_once_with("db-migrator", registry=reg)

    @pytest.mark.asyncio
    async def test_stream_output_uses_inline_prompt(self):
        """stream_output uses system_prompt kwarg when config has system_prompt_inline."""
        from src.engine.context import WebTaskContext
        from src.agents.config import AgentConfig

        reg = {
            "db-migrator": AgentConfig(
                name="db-migrator",
                system_prompt_file="",
                system_prompt_inline="You are a DB migration specialist.",
                source="project",
            ),
        }
        ctx = WebTaskContext(task_id=1, pool=MagicMock(), mode="autonomous", registry=reg)

        with patch("src.engine.context.get_agent_config", return_value=reg["db-migrator"]):
            with patch("src.engine.context.stream_claude") as mock_stream:
                async def _fake_stream(*a, **kw):
                    yield "output text"
                mock_stream.return_value = _fake_stream()
                with patch("src.engine.context.AgentOutputRepository"):
                    await ctx.stream_output("db-migrator", "migrate the DB", {})

                # Verify system_prompt (inline) was used, not system_prompt_file
                call_kwargs = mock_stream.call_args
                assert call_kwargs.kwargs.get("system_prompt") == "You are a DB migration specialist."
                assert call_kwargs.kwargs.get("system_prompt_file") is None

    @pytest.mark.asyncio
    async def test_stream_output_uses_file_prompt_for_core_agents(self):
        """stream_output uses system_prompt_file for core agents (no inline)."""
        from src.engine.context import WebTaskContext
        from src.agents.config import AgentConfig

        reg = {
            "plan": AgentConfig(
                name="plan",
                system_prompt_file="/path/to/plan.txt",
                source="default",
            ),
        }
        ctx = WebTaskContext(task_id=1, pool=MagicMock(), mode="autonomous", registry=reg)

        with patch("src.engine.context.get_agent_config", return_value=reg["plan"]):
            with patch("src.engine.context.stream_claude") as mock_stream:
                async def _fake_stream(*a, **kw):
                    yield "output text"
                mock_stream.return_value = _fake_stream()
                with patch("src.engine.context.AgentOutputRepository"):
                    await ctx.stream_output("plan", "create a plan", {})

                call_kwargs = mock_stream.call_args
                assert call_kwargs.kwargs.get("system_prompt_file") == "/path/to/plan.txt"
                assert call_kwargs.kwargs.get("system_prompt") is None


class TestOrchestrateWithRegistry:
    """orchestrate_pipeline with registry threads it through schema, decision, and validation."""

    @pytest.mark.asyncio
    async def test_registry_passed_to_schema_builder(self):
        """orchestrate_pipeline builds schema from provided registry."""
        from src.agents.config import AgentConfig, DEFAULT_REGISTRY

        custom_reg = dict(DEFAULT_REGISTRY)
        custom_reg["db-migrator"] = AgentConfig(
            name="db-migrator",
            system_prompt_file="",
            description="DB migrations",
            source="project",
        )

        ctx = MagicMock()
        ctx.mode = "autonomous"
        ctx.project_path = "."

        # stream_output returns sections
        async def fake_stream(*a, **kw):
            return {"DECISION": "APPROVED"}
        ctx.stream_output = AsyncMock(side_effect=fake_stream)
        ctx.update_status = AsyncMock()
        ctx.confirm_reroute = AsyncMock(return_value=True)
        ctx.handle_halt = AsyncMock(return_value="approve")

        # Mock the decision call to return "approved"
        decision_json = json.dumps({
            "result": json.dumps({
                "next_agent": "approved",
                "reasoning": "Looks good",
                "confidence": 0.9,
            })
        })

        with patch("src.pipeline.orchestrator.call_orchestrator_claude", new_callable=AsyncMock, return_value=decision_json) as mock_call:
            with patch("src.pipeline.orchestrator.build_orchestrator_schema") as mock_schema:
                mock_schema.return_value = ORCHESTRATOR_SCHEMA
                with patch("src.pipeline.orchestrator.build_orchestrator_system_prompt", return_value="dynamic prompt"):
                    await orchestrate_pipeline(ctx, "test prompt", None, 1, registry=custom_reg)

                # Verify schema was built with the custom registry
                mock_schema.assert_called_with(custom_reg)

    @pytest.mark.asyncio
    async def test_registry_none_uses_default(self):
        """orchestrate_pipeline with registry=None falls back to DEFAULT_REGISTRY."""
        ctx = MagicMock()
        ctx.mode = "autonomous"
        ctx.project_path = "."

        async def fake_stream(*a, **kw):
            return {"DECISION": "APPROVED"}
        ctx.stream_output = AsyncMock(side_effect=fake_stream)
        ctx.update_status = AsyncMock()
        ctx.confirm_reroute = AsyncMock(return_value=True)

        decision_json = json.dumps({
            "result": json.dumps({
                "next_agent": "approved",
                "reasoning": "Done",
                "confidence": 0.95,
            })
        })

        with patch("src.pipeline.orchestrator.call_orchestrator_claude", new_callable=AsyncMock, return_value=decision_json):
            with patch("src.pipeline.orchestrator.build_orchestrator_schema") as mock_schema:
                mock_schema.return_value = ORCHESTRATOR_SCHEMA
                with patch("src.pipeline.orchestrator.build_orchestrator_system_prompt", return_value="prompt"):
                    state = await orchestrate_pipeline(ctx, "test", None, 1)

                # Should have been called (with the default registry copy)
                mock_schema.assert_called()
                call_reg = mock_schema.call_args[0][0]
                # Should contain core agents
                assert "plan" in call_reg
                assert "execute" in call_reg


class TestProjectAgentRouting:
    """When orchestrator routes to a project agent, stream_output receives that agent name."""

    @pytest.mark.asyncio
    async def test_project_agent_receives_correct_name(self):
        """Routing to db-migrator calls stream_output with 'db-migrator'."""
        from src.agents.config import AgentConfig, DEFAULT_REGISTRY

        custom_reg = dict(DEFAULT_REGISTRY)
        custom_reg["db-migrator"] = AgentConfig(
            name="db-migrator",
            system_prompt_file="",
            system_prompt_inline="You are a DB migration specialist.",
            description="DB migrations",
            source="project",
            allowed_transitions=("plan", "execute", "test", "review", "approved"),
        )

        ctx = MagicMock()
        ctx.mode = "autonomous"
        ctx.project_path = "."

        call_count = 0
        async def fake_stream(agent_name, prompt, sections):
            nonlocal call_count
            call_count += 1
            return {"DECISION": "APPROVED", "HANDOFF": "done"}
        ctx.stream_output = AsyncMock(side_effect=fake_stream)
        ctx.update_status = AsyncMock()
        ctx.confirm_reroute = AsyncMock(return_value=True)

        # First call: routes to db-migrator, second call: approved
        responses = iter([
            json.dumps({"result": json.dumps({"next_agent": "db-migrator", "reasoning": "Need migration", "confidence": 0.9})}),
            json.dumps({"result": json.dumps({"next_agent": "approved", "reasoning": "Done", "confidence": 0.95})}),
        ])

        with patch("src.pipeline.orchestrator.call_orchestrator_claude", new_callable=AsyncMock, side_effect=lambda *a, **kw: next(responses)):
            with patch("src.pipeline.orchestrator.build_orchestrator_schema", return_value=ORCHESTRATOR_SCHEMA):
                with patch("src.pipeline.orchestrator.build_orchestrator_system_prompt", return_value="prompt"):
                    with patch("src.pipeline.orchestrator.validate_transition", side_effect=lambda f, t, **kw: t):
                        state = await orchestrate_pipeline(ctx, "migrate db", None, 1, registry=custom_reg)

        # stream_output should have been called with "db-migrator" at some point
        agent_names = [call.args[0] for call in ctx.stream_output.call_args_list]
        assert "db-migrator" in agent_names
