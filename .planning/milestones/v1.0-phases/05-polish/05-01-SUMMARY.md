---
phase: 05-polish
plan: 01
subsystem: infra
tags: [git, autocommit, tokens, cost-tracking, sqlite, asyncio]

requires:
  - phase: 03-tui-shell
    provides: StatusBar widget, streaming.py agent panel wiring
  - phase: 01-foundation
    provides: Database schema, repository pattern, runner subprocess
provides:
  - Git auto-commit module for post-approval cycle commits
  - AgentUsage dataclass and agent_usage DB table
  - UsageRepository for token/cost persistence
  - stream_claude result event dict yielding
  - StatusBar token/cost display via set_usage
affects: [05-polish]

tech-stack:
  added: []
  patterns: [result-event-dict-yield, usage-tracking-persistence]

key-files:
  created:
    - src/git/__init__.py
    - src/git/autocommit.py
    - tests/test_autocommit.py
    - tests/test_usage_tracking.py
  modified:
    - src/db/schema.py
    - src/db/repository.py
    - src/runner/runner.py
    - src/tui/status_bar.py
    - src/tui/streaming.py
    - tests/conftest.py
    - tests/test_runner.py

key-decisions:
  - "stream_claude yields result events as dict (isinstance check distinguishes text from metadata)"
  - "StatusBar.set_usage formats tokens as 'Xin/Yout' and cost as '$X.XXXX'"
  - "auto_commit uses asyncio.Lock to prevent concurrent git operations"
  - "git diff --cached --quiet exit code 0 means nothing staged (skip commit)"

patterns-established:
  - "Result event dict pattern: stream_claude yields mixed str|dict, callers check isinstance"
  - "Usage tracking: stream_agent_to_panel captures result dict and persists via UsageRepository"

requirements-completed: [INFR-06, INFR-07]

duration: 8min
completed: 2026-03-12
---

# Phase 5 Plan 1: Git Auto-commit and Token/Cost Tracking Summary

**Async git auto-commit with lock-guarded subprocess and token/cost tracking from Claude CLI result events into StatusBar and SQLite**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-12T15:00:49Z
- **Completed:** 2026-03-12T15:08:29Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments
- Git auto-commit module that stages, checks for changes, and commits with descriptive messages
- AgentUsage table and repository for persisting token/cost data per agent run
- stream_claude now yields result event dicts alongside text chunks
- StatusBar displays token counts and cost after each agent completes
- stream_agent_to_panel captures usage metadata and persists to DB

## Task Commits

Each task was committed atomically:

1. **Task 1: Git auto-commit module and token/cost tracking infrastructure** - `9c3559e` (test), `dbd6d78` (feat)
2. **Task 2: Wire token tracking into runner and status bar** - `21b9537` (test), `2f9e89a` (feat)

_Note: TDD tasks have RED (test) and GREEN (feat) commits_

## Files Created/Modified
- `src/git/__init__.py` - Git module package init
- `src/git/autocommit.py` - Async auto_commit with lock and .git detection
- `src/db/schema.py` - Added AgentUsage dataclass and agent_usage table SQL
- `src/db/repository.py` - Added UsageRepository with create/get_by_session
- `src/runner/runner.py` - stream_claude yields result event dicts
- `src/tui/status_bar.py` - set_usage method for token/cost display
- `src/tui/streaming.py` - Captures result events, updates status bar, persists usage
- `tests/conftest.py` - Added agent_usage table to db_conn fixture
- `tests/test_autocommit.py` - Tests for git auto-commit scenarios
- `tests/test_usage_tracking.py` - Tests for usage dataclass, repo, runner events, status bar
- `tests/test_runner.py` - Updated to handle new result event format

## Decisions Made
- stream_claude yields result events as dict (isinstance check distinguishes text from metadata)
- StatusBar.set_usage formats tokens as "Xin/Yout" and cost as "$X.XXXX"
- auto_commit uses asyncio.Lock to prevent concurrent git operations
- git diff --cached --quiet exit code 0 means nothing staged (skip commit)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing test_runner.py for new result event format**
- **Found during:** Task 2
- **Issue:** test_stream_lines_yielded expected only text chunks but now receives result dict too
- **Fix:** Updated assertion to filter text vs dict chunks
- **Files modified:** tests/test_runner.py
- **Verification:** All 139 tests pass
- **Committed in:** 2f9e89a (Task 2 commit)

**2. [Rule 1 - Bug] Fixed FK constraint in usage tracking tests**
- **Found during:** Task 1
- **Issue:** Usage tests inserted records with session_id=1 but no session existed (FK constraint)
- **Fix:** Added helper to create session before inserting usage records
- **Files modified:** tests/test_usage_tracking.py
- **Verification:** All usage tests pass
- **Committed in:** dbd6d78 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes necessary for test correctness. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Git auto-commit ready to be called after approved execution cycles
- Token/cost tracking infrastructure ready for display in UI
- All tests green (139 passed)

---
*Phase: 05-polish*
*Completed: 2026-03-12*
