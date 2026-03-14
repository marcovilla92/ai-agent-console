---
phase: 22-bug-fixes-foundation
verified: 2026-03-14T15:00:00Z
status: passed
score: 7/7 must-haves verified
re_verification: false
---

# Phase 22: Bug Fixes Foundation — Verification Report

**Phase Goal:** Agents follow their formatting rules and the orchestrator knows its routing role -- the pipeline produces structured, predictable output with bounded context growth
**Verified:** 2026-03-14T15:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                                               | Status     | Evidence                                                                                     |
| --- | ------------------------------------------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------- |
| 1   | Every agent call via stream_output passes the agent's system_prompt_file to stream_claude                          | ✓ VERIFIED | `get_agent_config(agent_name)` called at context.py:86, result passed as `system_prompt_file=system_prompt` at line 94 |
| 2   | Orchestrator routing decisions use orchestrator_system.txt via --system-prompt-file flag                            | ✓ VERIFIED | `ORCHESTRATOR_PROMPT_FILE` constant at orchestrator.py:80–82, passed to `call_orchestrator_claude` at line 195 |
| 3   | Unknown agent names fall back to running without system prompt (no crash)                                           | ✓ VERIFIED | `except KeyError` block at context.py:89–90 sets `system_prompt = None` with warning log    |
| 4   | Handoff context contains at most the last complete cycle (plan+execute+review) plus the pinned first plan handoff  | ✓ VERIFIED | `apply_handoff_windowing` keeps `pinned + handoffs[-MAX_HANDOFF_ENTRIES:]` (orchestrator.py:99–103) |
| 5   | Total windowed handoff characters (excluding pinned plan) stay under 8000                                           | ✓ VERIFIED | `while len(total) > MAX_HANDOFF_CHARS and len(windowed) > 1: windowed.pop(0)` at orchestrator.py:110–112 |
| 6   | The first plan handoff is never dropped regardless of how many iterations occur                                     | ✓ VERIFIED | `pinned = handoffs[0]` is always re-inserted at index 0 in both windowing passes             |
| 7   | On the first cycle (3 handoffs), windowing has no effect (correct behavior)                                         | ✓ VERIFIED | Guard condition `if len(handoffs) > MAX_HANDOFF_ENTRIES + 1` (> 4) means 3 handoffs are untouched |

**Score:** 7/7 truths verified

---

### Required Artifacts

| Artifact                          | Expected                                        | Status     | Details                                                                              |
| --------------------------------- | ----------------------------------------------- | ---------- | ------------------------------------------------------------------------------------ |
| `src/engine/context.py`           | stream_output with system prompt lookup         | ✓ VERIFIED | Imports `get_agent_config`, lookup with KeyError fallback, passes `system_prompt_file=` to `stream_claude` |
| `src/runner/runner.py`            | call_orchestrator_claude with system_prompt_file | ✓ VERIFIED | Signature at line 146: `system_prompt_file: str | None = None`; builds flag at lines 160–161 |
| `src/pipeline/orchestrator.py`    | Passes orchestrator prompt path to call_orchestrator_claude; bounded windowing | ✓ VERIFIED | `ORCHESTRATOR_PROMPT_FILE` at line 80, `MAX_HANDOFF_ENTRIES/CHARS` at lines 84–85, `apply_handoff_windowing()` at line 90, call site at line 301 |
| `tests/test_system_prompts.py`    | Unit tests for FIX-01 and FIX-02 (min 40 lines) | ✓ VERIFIED | 165 lines, 5 tests across 3 test classes; all 5 pass                                |
| `tests/test_handoff_windowing.py` | Unit tests for CTX-05 and CTX-06 (min 60 lines) | ✓ VERIFIED | 115 lines, 6 tests in TestHandoffWindowing; all 6 pass                              |

---

### Key Link Verification

| From                           | To                               | Via                                           | Status     | Details                                                                              |
| ------------------------------ | -------------------------------- | --------------------------------------------- | ---------- | ------------------------------------------------------------------------------------ |
| `src/engine/context.py`        | `src/agents/config.py`           | `get_agent_config(agent_name)`                | ✓ WIRED    | Import at line 24; call at line 86 with agent_name passed through                   |
| `src/engine/context.py`        | `src/runner/runner.py`           | `stream_claude(prompt, system_prompt_file=...)` | ✓ WIRED  | Pattern `system_prompt_file=system_prompt` present at line 94                       |
| `src/pipeline/orchestrator.py` | `src/runner/runner.py`           | `call_orchestrator_claude(prompt, schema, ORCHESTRATOR_PROMPT_FILE)` | ✓ WIRED | Pattern `ORCHESTRATOR_PROMPT_FILE` present at line 195 |
| `src/pipeline/orchestrator.py` | `state.accumulated_handoffs`     | windowing logic after append                  | ✓ WIRED    | `apply_handoff_windowing(state)` called at line 301 immediately after `append` at line 300; uses `MAX_HANDOFF_ENTRIES` |

---

### Requirements Coverage

| Requirement | Source Plan | Description                                                                                  | Status      | Evidence                                                                             |
| ----------- | ----------- | -------------------------------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------ |
| FIX-01      | 22-01       | All agents receive their system prompt files during web execution via `stream_output()`       | ✓ SATISFIED | `get_agent_config` lookup + `system_prompt_file=` kwarg wired in context.py:84–94   |
| FIX-02      | 22-01       | Orchestrator decision calls receive `orchestrator_system.txt` via `--system-prompt-file` flag | ✓ SATISFIED | `ORCHESTRATOR_PROMPT_FILE` constant + 3-arg call to `call_orchestrator_claude` at orchestrator.py:195 |
| CTX-05      | 22-02       | Handoffs are bounded to the last complete cycle (plan+execute+review) with 8000-char cap      | ✓ SATISFIED | `apply_handoff_windowing` enforces `MAX_HANDOFF_ENTRIES=3` and `MAX_HANDOFF_CHARS=8000` |
| CTX-06      | 22-02       | First plan handoff is pinned (exempt from windowing) to preserve original context on re-routes | ✓ SATISFIED | Index-0 pinning logic in both entry-count and char-cap passes of `apply_handoff_windowing` |

No orphaned requirements — all four IDs appear in plan frontmatter and have corresponding implementation evidence.

---

### Anti-Patterns Found

None. No TODO/FIXME/placeholder comments, no empty return stubs, no console-only handlers found in any of the five phase-modified files.

---

### Human Verification Required

None. All goal behaviors are verifiable programmatically through unit tests and static code inspection. The orchestrator_system.txt file exists at the path the constant resolves to (`src/agents/prompts/orchestrator_system.txt`), confirmed by directory listing.

---

### Test Suite Results

```
tests/test_system_prompts.py::TestStreamOutputSystemPrompt::test_known_agent_passes_system_prompt PASSED
tests/test_system_prompts.py::TestStreamOutputSystemPrompt::test_unknown_agent_falls_back_to_none PASSED
tests/test_system_prompts.py::TestCallOrchestratorSystemPrompt::test_builds_system_prompt_flag_when_provided PASSED
tests/test_system_prompts.py::TestCallOrchestratorSystemPrompt::test_omits_system_prompt_flag_when_none PASSED
tests/test_system_prompts.py::TestOrchestratorDecisionUsesPromptFile::test_passes_orchestrator_prompt_file PASSED
tests/test_handoff_windowing.py::TestHandoffWindowing::test_first_cycle_no_drop PASSED
tests/test_handoff_windowing.py::TestHandoffWindowing::test_second_cycle_windows_to_pinned_plus_recent PASSED
tests/test_handoff_windowing.py::TestHandoffWindowing::test_pinned_always_original_plan PASSED
tests/test_handoff_windowing.py::TestHandoffWindowing::test_char_cap_drops_oldest_windowed PASSED
tests/test_handoff_windowing.py::TestHandoffWindowing::test_pinned_exempt_from_char_cap PASSED
tests/test_handoff_windowing.py::TestHandoffWindowing::test_four_handoffs_keeps_all PASSED

11 passed in 0.08s
```

---

### Summary

Phase 22 fully achieves its goal. Both bugs in Plans 01 and 02 are fixed and wired end-to-end:

- **FIX-01/FIX-02** (Plan 01): The web execution path now passes system prompt files to every Claude CLI invocation — agents receive their formatting rules and the orchestrator receives its routing role definition. The plumbing that existed in `stream_claude` and `call_orchestrator_claude` is now actively used.

- **CTX-05/CTX-06** (Plan 02): `apply_handoff_windowing` is called after every handoff append in the orchestration loop, bounding context to `pinned[0] + last 3 entries` with an 8000-character cap on the sliding portion. The first plan handoff is exempt from all caps.

All four requirement IDs are satisfied. No stubs, no orphaned artifacts, no anti-patterns.

---

_Verified: 2026-03-14T15:00:00Z_
_Verifier: Claude (gsd-verifier)_
