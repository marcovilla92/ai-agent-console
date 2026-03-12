---
phase: 03-tui-shell
verified: 2026-03-12T14:00:00Z
status: gaps_found
score: 4/5 must-haves verified
gaps:
  - truth: "Agent output streams into the corresponding panel line-by-line in real-time (not displayed only after completion)"
    status: failed
    reason: "start_agent_worker() in streaming.py is fully implemented but never called from app.py or actions.py. Keyboard actions (Ctrl+S, Ctrl+P/E/R) call prepare_agent_run() then exit with a comment saying the streaming worker handles it -- but the import and call are absent. Streaming is tested in isolation but is orphaned from the live action path."
    artifacts:
      - path: "src/tui/app.py"
        issue: "run_agent() calls prepare_agent_run() then returns with comment '# Actual agent execution is handled by streaming worker (Plan 03-03)' -- but start_agent_worker is never imported or called"
      - path: "src/tui/actions.py"
        issue: "send_prompt() calls prepare_agent_run() and returns -- no streaming worker invocation"
      - path: "src/tui/streaming.py"
        issue: "start_agent_worker() defined and complete but has zero callers in production code (only called from within streaming.py itself via _run_agent)"
    missing:
      - "Import start_agent_worker from src.tui.streaming in app.py or actions.py"
      - "Call start_agent_worker(app, agent_name, prompt) inside run_agent() after prepare_agent_run() returns a prompt"
      - "Wire send_prompt() to call start_agent_worker(app, 'plan', prompt) to start the full pipeline"
human_verification:
  - test: "Press Ctrl+S with a prompt entered"
    expected: "Plan panel starts filling with streamed Claude output line by line; status bar shows 'streaming'"
    why_human: "Once the wiring gap is closed, visual confirmation of live streaming behavior requires a real terminal run"
  - test: "Press Tab repeatedly"
    expected: "Focus cycles visibly across all four panels with terminal focus indicator moving"
    why_human: "Focus appearance in the rendered TUI cannot be verified programmatically"
---

# Phase 3: TUI Shell Verification Report

**Phase Goal:** Users interact with the agent pipeline through a 4-panel terminal interface with real-time streaming and keyboard-driven workflow
**Verified:** 2026-03-12T14:00:00Z
**Status:** gaps_found
**Re-verification:** No -- initial verification

---

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User sees four distinct panels (Prompt, Plan, Execute, Review) in a Textual-based terminal application | VERIFIED | `app.py:compose()` yields PromptPanel + 3 OutputPanels; 8 layout tests pass |
| 2 | Agent output streams into the corresponding panel line-by-line in real-time (not displayed only after completion) | FAILED | `start_agent_worker()` exists and is implemented in `streaming.py` but is never called from `app.py` or `actions.py`; pressing Ctrl+S/P/E/R only calls `prepare_agent_run()` and returns |
| 3 | User navigates between panels with Tab and triggers actions with Ctrl+S (send), Ctrl+P (plan), Ctrl+E (execute), Ctrl+R (review) | VERIFIED | BINDINGS in `app.py` confirmed; focus cycling tested; note: plan specified Ctrl+Enter, implementation uses Ctrl+S (documented deviation in SUMMARY) |
| 4 | Status bar at the bottom shows the current agent name, workflow state, step description, and suggested next action | VERIFIED | `status_bar.py` implements `set_status()` and `display_text`; 2 tests confirm field rendering; minor bug: initial hint text says "Ctrl+Enter" instead of "Ctrl+S" |
| 5 | Interface renders with a dark theme by default | VERIFIED | `THEME = "textual-dark"` in `app.py`; `theme.tcss` applies `$surface-darken-1` backgrounds; test_app_dark_theme passes |

**Score:** 4/5 truths verified (1 gap)

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/tui/__init__.py` | Package init | VERIFIED | Exists |
| `src/tui/app.py` | AgentConsoleApp with 4-panel compose, key bindings | VERIFIED | 106 lines, substantive, bindings wired to actions |
| `src/tui/panels.py` | PromptPanel (TextArea), OutputPanel (RichLog) | VERIFIED | Both classes implemented with correct Textual base classes |
| `src/tui/theme.tcss` | Dark theme, 2x2 grid layout | VERIFIED | CSS grid-size 2 2, surface-darken backgrounds |
| `src/tui/status_bar.py` | StatusBar with agent/state/step/next_action | VERIFIED | set_status(), display_text, on_mount refresh all present |
| `src/tui/actions.py` | Action handlers bridging TUI events to pipeline | PARTIAL | Handlers exist but do not call start_agent_worker; bridge is incomplete |
| `src/tui/streaming.py` | Async worker streaming Claude output into panels | ORPHANED | Fully implemented but never called from production code paths |
| `tests/test_tui_layout.py` | Layout structure and theme tests | VERIFIED | 8 tests, all passing |
| `tests/test_tui_keys.py` | Keyboard binding and action dispatch tests | VERIFIED | 14 tests, all passing |
| `tests/test_tui_streaming.py` | Streaming worker tests | VERIFIED | 5 tests, all passing (test streaming.py directly, not via app actions) |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app.py:action_send_prompt` | `actions.send_prompt()` | direct call | WIRED | `send_prompt(self)` called at line 86 |
| `app.py:action_run_plan/execute/review` | `actions.prepare_agent_run()` | `run_agent()` | WIRED | `prepare_agent_run(self, agent_name)` called at line 102 |
| `actions.prepare_agent_run` | `streaming.start_agent_worker` | should be call after prompt validation | NOT WIRED | No import of streaming module in actions.py or app.py; `start_agent_worker` has zero callers in production |
| `streaming.start_agent_worker` | `runner.stream_claude` | `stream_agent_to_panel` async-for | WIRED | `async for chunk in stream_claude(...)` at streaming.py:50; `panel.write(chunk)` at line 56 |
| `streaming.start_agent_worker` | `status_bar.set_status` | `complete_agent_run` call | WIRED | `complete_agent_run(app, agent_name, success=True)` at streaming.py:100 |
| `app.py:status_bar` | `status_bar.StatusBar` | query_one | WIRED | `query_one("#status-bar", StatusBar)` |

**Critical broken link:** `app keyboard action -> streaming.start_agent_worker` is NOT wired. Every user-facing keyboard shortcut terminates at `prepare_agent_run()` without launching the streaming worker.

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TUI-01 | 03-01 | User sees 4-panel layout (Prompt, Plan, Execute, Review) | SATISFIED | `app.py:compose()` verified; 4 panel tests pass |
| TUI-02 | 03-02 | Tab navigation between panels | SATISFIED | `("tab", "cycle_focus")` binding; `action_cycle_focus()` with wrap-around; tests pass |
| TUI-03 | 03-02 | Keyboard shortcuts (Ctrl+Enter send, Ctrl+P/E/R agents) | PARTIAL | Ctrl+P/E/R wired; send uses Ctrl+S not Ctrl+Enter (documented deviation); but all bindings terminate before streaming starts |
| TUI-04 | 03-03 | Status bar with agent name, state, step, next action | SATISFIED | `status_bar.py` implements all four fields; `set_status()` API; tests pass |
| TUI-06 | 03-01 | Dark theme by default | SATISFIED | `THEME = "textual-dark"`; `theme.tcss` with surface-darken styling |
| INFR-02 | 03-03 | Streaming output displays line-by-line in real-time in TUI panels | BLOCKED | `stream_agent_to_panel()` does write line-by-line but is not connected to the keyboard action path; no user gesture can trigger it in production |

**Orphaned requirements check:** No additional requirements mapped to Phase 3 in REQUIREMENTS.md beyond the six listed above. All six accounted for.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/tui/app.py` | 105 | Comment `# Actual agent execution is handled by streaming worker (Plan 03-03)` — the plan completed but the call was never added | Blocker | All keyboard triggers silently do nothing after status bar update |
| `src/tui/status_bar.py` | 27 | Initial hint text `"Enter a prompt and press Ctrl+Enter"` — binding was changed to Ctrl+S | Warning | User sees wrong keyboard shortcut in the status bar on first launch |

---

## Human Verification Required

### 1. Real-time streaming visual

**Test:** After the wiring gap is closed, launch the app (`python -m src.tui.app`), enter any prompt, press Ctrl+S
**Expected:** Plan panel begins showing output line by line while Claude CLI is running; status bar shows "streaming"; panel does not wait for completion before displaying
**Why human:** Visual confirmation of line-by-line appearance requires a live terminal session

### 2. Tab focus cycling visual

**Test:** Press Tab four times
**Expected:** Visible focus indicator moves through Prompt -> Plan -> Execute -> Review -> Prompt (wraps)
**Why human:** Terminal focus appearance cannot be asserted programmatically

---

## Gaps Summary

**One blocking gap prevents goal achievement.**

The streaming worker (`src/tui/streaming.py`) is fully implemented and tested in isolation. It correctly streams Claude CLI output chunk-by-chunk into an OutputPanel via `stream_agent_to_panel()`, and `start_agent_worker()` wraps this in a Textual background worker with status bar updates. However, this module is never imported or called from the keyboard action path in `app.py` or `actions.py`.

When a user presses Ctrl+S, Ctrl+P, Ctrl+E, or Ctrl+R:
1. `prepare_agent_run()` validates the prompt, clears the panel, updates the status bar to "running"
2. Control returns to the app
3. Nothing happens — no Claude CLI subprocess is launched, no output appears

The fix is a targeted wiring change: import `start_agent_worker` in `app.py` (or `actions.py`) and call it with the agent name and prompt after `prepare_agent_run()` returns successfully.

This gap means the core interactive capability — users seeing agent output stream into panels — does not work despite the streaming machinery being correct. TUI-04 (status bar) and TUI-01/TUI-02/TUI-06 (layout, nav, theme) are all achieved. INFR-02 and the streaming path in TUI-03 are blocked.

A secondary cosmetic issue: `status_bar.py` still shows "Ctrl+Enter" in the default hint text, which should be "Ctrl+S".

---

_Verified: 2026-03-12T14:00:00Z_
_Verifier: Claude (gsd-verifier)_
