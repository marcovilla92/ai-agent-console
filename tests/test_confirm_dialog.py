"""
Tests for modal confirmation dialogs and orchestrator TUI wiring.

Tests RerouteConfirmDialog, HaltDialog, show_reroute_confirmation,
show_halt_dialog, start_orchestrator_worker, and send_prompt orchestrator routing.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.pipeline.orchestrator import OrchestratorDecision, OrchestratorState


# --- RerouteConfirmDialog ---

class TestRerouteConfirmDialog:
    def test_creates_with_agent_and_reasoning(self):
        from src.tui.confirm_dialog import RerouteConfirmDialog

        dialog = RerouteConfirmDialog(agent="execute", reasoning="Plan looks good")
        assert dialog.agent == "execute"
        assert dialog.reasoning == "Plan looks good"

    def test_is_modal_screen(self):
        from src.tui.confirm_dialog import RerouteConfirmDialog
        from textual.screen import ModalScreen

        dialog = RerouteConfirmDialog(agent="plan", reasoning="test")
        assert isinstance(dialog, ModalScreen)


# --- HaltDialog ---

class TestHaltDialog:
    def test_creates_with_iterations(self):
        from src.tui.confirm_dialog import HaltDialog

        dialog = HaltDialog(iterations=3)
        assert dialog.iterations == 3

    def test_is_modal_screen(self):
        from src.tui.confirm_dialog import HaltDialog
        from textual.screen import ModalScreen

        dialog = HaltDialog(iterations=5)
        assert isinstance(dialog, ModalScreen)


# --- show_reroute_confirmation ---

class TestShowRerouteConfirmation:
    @pytest.mark.asyncio
    async def test_calls_push_screen_with_dialog(self):
        from src.pipeline.orchestrator import show_reroute_confirmation
        from src.tui.confirm_dialog import RerouteConfirmDialog

        decision = OrchestratorDecision(
            next_agent="plan",
            reasoning="Needs revision",
            confidence=0.8,
            full_response="{}",
        )

        app = MagicMock()
        # Simulate: app.call_from_thread calls the callback immediately with True
        def fake_call_from_thread(fn, *args, **kwargs):
            # fn is app.push_screen, args[0] is dialog, args[1] is callback
            callback = args[1]
            callback(True)

        app.call_from_thread = MagicMock(side_effect=fake_call_from_thread)

        result = await show_reroute_confirmation(app, decision)
        assert result is True
        app.call_from_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_on_cancel(self):
        from src.pipeline.orchestrator import show_reroute_confirmation

        decision = OrchestratorDecision(
            next_agent="execute",
            reasoning="test",
            confidence=0.8,
            full_response="{}",
        )

        app = MagicMock()
        def fake_call_from_thread(fn, *args, **kwargs):
            callback = args[1]
            callback(False)

        app.call_from_thread = MagicMock(side_effect=fake_call_from_thread)

        result = await show_reroute_confirmation(app, decision)
        assert result is False


# --- show_halt_dialog ---

class TestShowHaltDialog:
    @pytest.mark.asyncio
    async def test_returns_user_choice(self):
        from src.pipeline.orchestrator import show_halt_dialog

        state = OrchestratorState(session_id=1, original_prompt="test")
        state.iteration_count = 3

        app = MagicMock()
        def fake_call_from_thread(fn, *args, **kwargs):
            callback = args[1]
            callback("stop")

        app.call_from_thread = MagicMock(side_effect=fake_call_from_thread)

        result = await show_halt_dialog(app, state)
        assert result == "stop"

    @pytest.mark.asyncio
    async def test_returns_continue(self):
        from src.pipeline.orchestrator import show_halt_dialog

        state = OrchestratorState(session_id=1, original_prompt="test")
        state.iteration_count = 3

        app = MagicMock()
        def fake_call_from_thread(fn, *args, **kwargs):
            callback = args[1]
            callback("continue")

        app.call_from_thread = MagicMock(side_effect=fake_call_from_thread)

        result = await show_halt_dialog(app, state)
        assert result == "continue"


# --- send_prompt uses orchestrator ---

class TestSendPromptOrchestrator:
    def test_send_prompt_calls_orchestrator_worker(self):
        from src.tui.actions import send_prompt

        app = MagicMock()
        app.prompt_panel.text = "Build something cool"
        app.get_panel.return_value = MagicMock()

        with patch("src.tui.streaming.start_orchestrator_worker") as mock_worker:
            result = send_prompt(app)
            assert result == "Build something cool"
            mock_worker.assert_called_once()


# --- start_orchestrator_worker ---

class TestStartOrchestratorWorker:
    def test_start_orchestrator_worker_importable(self):
        from src.tui.streaming import start_orchestrator_worker
        assert callable(start_orchestrator_worker)


# --- orchestrate_pipeline status bar ---

class TestOrchestratorStatusBar:
    @pytest.mark.asyncio
    async def test_status_bar_updated_with_reasoning(self):
        """orchestrate_pipeline updates status bar after each decision."""
        app = MagicMock()
        app.get_panel.return_value = MagicMock()
        app.status_bar = MagicMock()
        app.project_path = "/tmp"

        decision_json = '{"result": "{\\"next_agent\\": \\"approved\\", \\"reasoning\\": \\"All good\\", \\"confidence\\": 0.9}"}'

        with patch(
            "src.tui.streaming.stream_agent_to_panel",
            new_callable=AsyncMock,
            return_value={"PLAN": "some plan output"},
        ), patch(
            "src.pipeline.orchestrator.call_orchestrator_claude",
            new_callable=AsyncMock,
            return_value=decision_json,
        ), patch(
            "src.pipeline.orchestrator.log_decision",
            new_callable=AsyncMock,
        ):
            from src.pipeline.orchestrator import orchestrate_pipeline

            state = await orchestrate_pipeline(app, "test prompt", MagicMock(), 1)

            # Status bar should have been called with orchestrator routing info
            routing_calls = [
                c for c in app.status_bar.set_status.call_args_list
                if c[1].get("agent") == "orchestrator"
            ]
            assert len(routing_calls) >= 1
            assert "All good" in routing_calls[0][1]["step"]


# --- orchestrate_pipeline with reroute confirmation ---

class TestOrchestratorRerouteIntegration:
    @pytest.mark.asyncio
    async def test_reroute_calls_confirmation_dialog(self):
        """When review re-routes, show_reroute_confirmation is called."""
        app = MagicMock()
        app.get_panel.return_value = MagicMock()
        app.status_bar = MagicMock()
        app.project_path = "/tmp"

        # Flow: plan -> execute -> review -> (re-route to plan) -> approved
        call_count = 0
        async def fake_get_decision(state, sections):
            nonlocal call_count
            call_count += 1
            if state.current_agent == "plan" and call_count == 1:
                return OrchestratorDecision(
                    next_agent="execute", reasoning="Proceed", confidence=0.9, full_response="{}",
                )
            if state.current_agent == "execute":
                return OrchestratorDecision(
                    next_agent="review", reasoning="Code ready", confidence=0.9, full_response="{}",
                )
            if state.current_agent == "review" and call_count <= 4:
                return OrchestratorDecision(
                    next_agent="plan", reasoning="Needs revision", confidence=0.8, full_response="{}",
                )
            return OrchestratorDecision(
                next_agent="approved", reasoning="All good now", confidence=0.95, full_response="{}",
            )

        with patch(
            "src.tui.streaming.stream_agent_to_panel",
            new_callable=AsyncMock,
            return_value={"OUTPUT": "content"},
        ), patch(
            "src.pipeline.orchestrator.get_orchestrator_decision",
            side_effect=fake_get_decision,
        ), patch(
            "src.pipeline.orchestrator.log_decision",
            new_callable=AsyncMock,
        ), patch(
            "src.pipeline.orchestrator.show_reroute_confirmation",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_confirm:
            from src.pipeline.orchestrator import orchestrate_pipeline

            state = await orchestrate_pipeline(app, "test", MagicMock(), 1)
            # Confirmation dialog should have been called when review re-routed
            mock_confirm.assert_called()

    @pytest.mark.asyncio
    async def test_halt_dialog_called_at_iteration_limit(self):
        """After 3 iterations, show_halt_dialog is called."""
        app = MagicMock()
        app.get_panel.return_value = MagicMock()
        app.status_bar = MagicMock()
        app.project_path = "/tmp"

        # Always re-route to plan from review
        async def fake_get_decision(state, sections):
            if state.current_agent == "review":
                return OrchestratorDecision(
                    next_agent="plan",
                    reasoning="Needs more work",
                    confidence=0.7,
                    full_response="{}",
                )
            # Forward progression
            next_map = {"plan": "execute", "execute": "review"}
            return OrchestratorDecision(
                next_agent=next_map.get(state.current_agent, "review"),
                reasoning="Proceeding",
                confidence=0.9,
                full_response="{}",
            )

        with patch(
            "src.tui.streaming.stream_agent_to_panel",
            new_callable=AsyncMock,
            return_value={"OUTPUT": "content"},
        ), patch(
            "src.pipeline.orchestrator.get_orchestrator_decision",
            side_effect=fake_get_decision,
        ), patch(
            "src.pipeline.orchestrator.log_decision",
            new_callable=AsyncMock,
        ), patch(
            "src.pipeline.orchestrator.show_reroute_confirmation",
            new_callable=AsyncMock,
            return_value=True,
        ), patch(
            "src.pipeline.orchestrator.show_halt_dialog",
            new_callable=AsyncMock,
            return_value="stop",
        ) as mock_halt:
            from src.pipeline.orchestrator import orchestrate_pipeline

            state = await orchestrate_pipeline(app, "test", MagicMock(), 1)
            mock_halt.assert_called_once()
            assert state.halted is True
