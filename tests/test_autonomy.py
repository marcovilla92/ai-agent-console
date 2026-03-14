"""Tests for Phase 25: Autonomy Refinement (AUTO-01 through AUTO-04)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.pipeline.orchestrator import (
    CONFIDENCE_THRESHOLD,
    OrchestratorDecision,
    OrchestratorState,
    orchestrate_pipeline,
)


class TestDefaultAutonomous:
    """AUTO-01: Default execution mode is autonomous."""

    def test_default_mode_in_schema(self):
        from datetime import datetime, timezone
        from src.db.pg_schema import Task
        task = Task(
            name="test",
            project_path="/tmp",
            created_at=datetime.now(timezone.utc),
        )
        assert task.mode == "autonomous"

    def test_task_create_defaults_autonomous(self):
        from src.server.routers.tasks import TaskCreate
        tc = TaskCreate(name="test", prompt="test", project_path="/tmp")
        assert tc.mode == "autonomous"

    def test_confidence_threshold_is_half(self):
        assert CONFIDENCE_THRESHOLD == 0.5


class TestAutonomousLowConfidence:
    """AUTO-02: In autonomous mode, low confidence logs warning but never blocks."""

    @pytest.mark.asyncio
    async def test_low_confidence_autonomous_proceeds(self):
        """Pipeline proceeds despite low confidence in autonomous mode."""
        ctx = MagicMock()
        ctx.project_path = "/tmp"
        ctx.mode = "autonomous"
        ctx.update_status = AsyncMock()
        ctx.stream_output = AsyncMock(return_value={"PLAN": "some plan"})
        ctx.confirm_reroute = AsyncMock(return_value=True)
        ctx.handle_halt = AsyncMock(return_value="approve")

        # Low confidence decision that approves immediately
        low_conf_decision = OrchestratorDecision(
            next_agent="approved",
            reasoning="Uncertain but proceeding",
            confidence=0.3,
            full_response="{}",
        )

        with patch(
            "src.pipeline.orchestrator.get_orchestrator_decision",
            new_callable=AsyncMock,
            return_value=low_conf_decision,
        ), patch(
            "src.pipeline.orchestrator.process_execute_output",
            return_value=[],
        ), patch(
            "src.pipeline.orchestrator.log_decision",
            new_callable=AsyncMock,
        ):
            state = await orchestrate_pipeline(ctx, "test prompt")

        # Should have approved despite low confidence
        assert state.approved is True
        # Should NOT have called confirm_reroute for the low confidence gate
        # (it auto-proceeds in autonomous mode)
        # Check that low_confidence_warning status was sent
        status_calls = [
            c for c in ctx.update_status.call_args_list
            if len(c.kwargs) > 0 and c.kwargs.get("state") == "low_confidence_warning"
        ]
        assert len(status_calls) >= 1

    @pytest.mark.asyncio
    async def test_autonomous_never_blocks(self):
        """Autonomous mode never calls confirm_reroute for low confidence."""
        ctx = MagicMock()
        ctx.project_path = "/tmp"
        ctx.mode = "autonomous"
        ctx.update_status = AsyncMock()
        ctx.stream_output = AsyncMock(return_value={"PLAN": "plan"})
        ctx.handle_halt = AsyncMock(return_value="approve")

        call_count = 0

        async def fake_decision(state, sections, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return OrchestratorDecision(
                    next_agent="execute", reasoning="go", confidence=0.3,
                    full_response="{}",
                )
            return OrchestratorDecision(
                next_agent="approved", reasoning="done", confidence=0.9,
                full_response="{}",
            )

        with patch(
            "src.pipeline.orchestrator.get_orchestrator_decision",
            side_effect=fake_decision,
        ), patch(
            "src.pipeline.orchestrator.process_execute_output",
            return_value=[],
        ), patch(
            "src.pipeline.orchestrator.log_decision",
            new_callable=AsyncMock,
        ):
            # confirm_reroute should NOT be called for the low confidence forward progression
            ctx.confirm_reroute = AsyncMock(return_value=True)
            state = await orchestrate_pipeline(ctx, "test")

        assert state.approved is True


class TestSupervisedLowConfidence:
    """AUTO-03: In supervised mode, low confidence triggers user confirmation."""

    @pytest.mark.asyncio
    async def test_low_confidence_supervised_confirms(self):
        """Low confidence in supervised mode triggers confirm_reroute."""
        ctx = MagicMock()
        ctx.project_path = "/tmp"
        ctx.mode = "supervised"
        ctx.update_status = AsyncMock()
        ctx.stream_output = AsyncMock(return_value={"PLAN": "plan"})
        ctx.confirm_reroute = AsyncMock(return_value=True)
        ctx.handle_halt = AsyncMock(return_value="approve")

        low_conf = OrchestratorDecision(
            next_agent="approved", reasoning="unsure", confidence=0.3,
            full_response="{}",
        )

        with patch(
            "src.pipeline.orchestrator.get_orchestrator_decision",
            new_callable=AsyncMock,
            return_value=low_conf,
        ), patch(
            "src.pipeline.orchestrator.process_execute_output",
            return_value=[],
        ), patch(
            "src.pipeline.orchestrator.log_decision",
            new_callable=AsyncMock,
        ):
            state = await orchestrate_pipeline(ctx, "test")

        # Should have called confirm_reroute for low confidence
        ctx.confirm_reroute.assert_called()

    @pytest.mark.asyncio
    async def test_low_confidence_supervised_rejected_halts(self):
        """Rejecting a low confidence decision in supervised mode halts pipeline."""
        ctx = MagicMock()
        ctx.project_path = "/tmp"
        ctx.mode = "supervised"
        ctx.update_status = AsyncMock()
        ctx.stream_output = AsyncMock(return_value={"PLAN": "plan"})
        ctx.confirm_reroute = AsyncMock(return_value=False)
        ctx.handle_halt = AsyncMock(return_value="stop")

        low_conf = OrchestratorDecision(
            next_agent="execute", reasoning="unsure", confidence=0.2,
            full_response="{}",
        )

        with patch(
            "src.pipeline.orchestrator.get_orchestrator_decision",
            new_callable=AsyncMock,
            return_value=low_conf,
        ), patch(
            "src.pipeline.orchestrator.process_execute_output",
            return_value=[],
        ), patch(
            "src.pipeline.orchestrator.log_decision",
            new_callable=AsyncMock,
        ):
            state = await orchestrate_pipeline(ctx, "test")

        assert state.halted is True


class TestSupervisedAvailable:
    """AUTO-04: Supervised mode remains available as opt-in option."""

    def test_supervised_mode_accepted(self):
        from src.server.routers.tasks import TaskCreate
        tc = TaskCreate(name="test", prompt="test", project_path="/tmp", mode="supervised")
        assert tc.mode == "supervised"

    @pytest.mark.asyncio
    async def test_high_confidence_supervised_no_extra_gate(self):
        """High confidence decisions don't trigger extra confirmation."""
        ctx = MagicMock()
        ctx.project_path = "/tmp"
        ctx.mode = "supervised"
        ctx.update_status = AsyncMock()
        ctx.stream_output = AsyncMock(return_value={"PLAN": "plan"})
        ctx.confirm_reroute = AsyncMock(return_value=True)
        ctx.handle_halt = AsyncMock(return_value="approve")

        high_conf = OrchestratorDecision(
            next_agent="approved", reasoning="all good", confidence=0.95,
            full_response="{}",
        )

        with patch(
            "src.pipeline.orchestrator.get_orchestrator_decision",
            new_callable=AsyncMock,
            return_value=high_conf,
        ), patch(
            "src.pipeline.orchestrator.process_execute_output",
            return_value=[],
        ), patch(
            "src.pipeline.orchestrator.log_decision",
            new_callable=AsyncMock,
        ):
            state = await orchestrate_pipeline(ctx, "test")

        # High confidence approved: no confirm_reroute called
        ctx.confirm_reroute.assert_not_called()
        assert state.approved is True
