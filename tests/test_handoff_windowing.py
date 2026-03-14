"""Tests for handoff windowing logic (CTX-05, CTX-06).

Verifies bounded handoff windowing with pinned first plan handoff.
"""
import pytest

from src.pipeline.orchestrator import (
    OrchestratorState,
    apply_handoff_windowing,
    MAX_HANDOFF_ENTRIES,
    MAX_HANDOFF_CHARS,
)


def _make_handoff(agent: str, index: int, size: int = 100) -> str:
    """Create a fake handoff string of approximately `size` characters."""
    header = f"=== HANDOFF FROM {agent.upper()} ==="
    footer = f"=== END HANDOFF FROM {agent.upper()} ==="
    body = f"Handoff #{index} content. "
    # Pad to reach target size
    padding = "x" * max(0, size - len(header) - len(footer) - len(body) - 4)
    return f"{header}\n{body}{padding}\n{footer}"


def _make_state(handoffs: list[str]) -> OrchestratorState:
    """Create an OrchestratorState with the given handoffs."""
    state = OrchestratorState(session_id=1, original_prompt="test")
    state.accumulated_handoffs = list(handoffs)  # copy
    return state


class TestHandoffWindowing:
    """Tests for apply_handoff_windowing."""

    def test_first_cycle_no_drop(self):
        """With 3 handoffs (first cycle: plan, execute, review), windowing does NOT drop any."""
        handoffs = [
            _make_handoff("PLAN", 0),
            _make_handoff("EXECUTE", 1),
            _make_handoff("REVIEW", 2),
        ]
        state = _make_state(handoffs)
        apply_handoff_windowing(state)

        assert len(state.accumulated_handoffs) == 3
        for i, h in enumerate(handoffs):
            assert state.accumulated_handoffs[i] == h

    def test_second_cycle_windows_to_pinned_plus_recent(self):
        """With 7 handoffs (2+ cycles), only pinned[0] + last 3 remain (4 total)."""
        agents = ["PLAN", "EXECUTE", "REVIEW", "PLAN", "EXECUTE", "REVIEW", "PLAN"]
        handoffs = [_make_handoff(a, i) for i, a in enumerate(agents)]
        state = _make_state(handoffs)
        apply_handoff_windowing(state)

        assert len(state.accumulated_handoffs) == 4  # pinned + last 3
        assert state.accumulated_handoffs[0] == handoffs[0]  # pinned original plan
        assert state.accumulated_handoffs[1] == handoffs[4]  # last 3
        assert state.accumulated_handoffs[2] == handoffs[5]
        assert state.accumulated_handoffs[3] == handoffs[6]

    def test_pinned_always_original_plan(self):
        """Pinned handoff (index 0) is always the original plan handoff content."""
        handoffs = [_make_handoff("PLAN", i) for i in range(10)]
        original_plan = handoffs[0]
        state = _make_state(handoffs)
        apply_handoff_windowing(state)

        assert state.accumulated_handoffs[0] == original_plan
        assert "HANDOFF FROM PLAN" in state.accumulated_handoffs[0]

    def test_char_cap_drops_oldest_windowed(self):
        """When windowed portion exceeds 8000 chars, oldest windowed entries are dropped."""
        pinned = _make_handoff("PLAN", 0, size=100)
        # 3 windowed entries each 4000 chars => 12000+ chars total > 8000
        windowed = [_make_handoff("EXECUTE", i, size=4000) for i in range(1, 4)]
        state = _make_state([pinned] + windowed)

        # State has 4 entries: pinned + 3 windowed (within MAX_HANDOFF_ENTRIES + 1)
        # But char cap should drop oldest windowed until under 8000
        apply_handoff_windowing(state)

        # Pinned must be present
        assert state.accumulated_handoffs[0] == pinned
        # Windowed portion total must be <= MAX_HANDOFF_CHARS
        windowed_portion = state.accumulated_handoffs[1:]
        windowed_total = len("\n\n".join(windowed_portion))
        assert windowed_total <= MAX_HANDOFF_CHARS
        # At least one windowed entry should remain
        assert len(windowed_portion) >= 1

    def test_pinned_exempt_from_char_cap(self):
        """Pinned handoff's chars do not count toward the 8000-char cap."""
        pinned = _make_handoff("PLAN", 0, size=5000)  # 5000 chars, exempt
        # 2 windowed entries 3000 chars each => 6000 chars < 8000 cap
        windowed = [_make_handoff("EXECUTE", i, size=3000) for i in range(1, 3)]
        state = _make_state([pinned] + windowed)
        apply_handoff_windowing(state)

        # All 3 should remain: pinned (5000) + 2 windowed (6000 < 8000)
        assert len(state.accumulated_handoffs) == 3
        assert state.accumulated_handoffs[0] == pinned

    def test_four_handoffs_keeps_all(self):
        """With exactly MAX_HANDOFF_ENTRIES + 1 (4 handoffs), all are kept."""
        agents = ["PLAN", "EXECUTE", "REVIEW", "PLAN"]
        handoffs = [_make_handoff(a, i) for i, a in enumerate(agents)]
        state = _make_state(handoffs)
        apply_handoff_windowing(state)

        # pinned + 3 = 4 total, exactly at limit, no drop
        assert len(state.accumulated_handoffs) == 4
        for i, h in enumerate(handoffs):
            assert state.accumulated_handoffs[i] == h
