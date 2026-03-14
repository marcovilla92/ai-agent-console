---
phase: 29-ai-template-generation
plan: 01
subsystem: api
tags: [claude-cli, structured-output, asyncio, template-generation, fastapi]

requires:
  - phase: 26-project-agents
    provides: discover_project_agents loader, PROTECTED_AGENTS frozenset
  - phase: 27-project-commands
    provides: discover_project_commands loader
  - phase: 28-orchestrator-dynamic-registry
    provides: call_orchestrator_claude with structured output support

provides:
  - POST /templates/generate endpoint for AI-driven template creation
  - Template generation system prompt
  - Generated file validation via existing loaders
  - Concurrency control with asyncio.Lock (separate from pipeline)

affects: [30-template-editor, frontend-template-ui]

tech-stack:
  added: []
  patterns: [asyncio.Lock for single-resource concurrency, temp-dir validation via existing loaders]

key-files:
  created:
    - src/agents/prompts/template_gen_system.txt
  modified:
    - src/server/routers/templates.py

key-decisions:
  - "asyncio.Lock (not Semaphore) for generation concurrency -- simpler API with locked() check"
  - "Validation writes to tempdir and runs discover_project_agents/commands -- reuses existing loaders"
  - "System prompt is plain text (~50 lines), no Jinja2 templating in prompts"

patterns-established:
  - "Non-blocking lock check pattern: if lock.locked() -> 429, then async with lock"
  - "Temp directory validation: write generated files, run loaders, collect errors, cleanup"

requirements-completed: [AIGEN-01, AIGEN-02, AIGEN-03]

duration: 2min
completed: 2026-03-14
---

# Phase 29 Plan 01: AI Template Generation Summary

**POST /templates/generate endpoint with Claude CLI structured output, asyncio.Lock concurrency control, and temp-dir validation via existing agent/command loaders**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-14T18:47:11Z
- **Completed:** 2026-03-14T18:49:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- System prompt instructs Claude to generate complete templates with required files, reserved name warnings, and structured JSON output
- POST /templates/generate endpoint with full request/response models, 120s timeout, 502 on invalid AI response
- asyncio.Lock prevents concurrent generation (429 with Retry-After: 30)
- _validate_generated_files checks path safety, reserved agent names, and runs discover_project_agents/commands against temp dir

## Task Commits

Each task was committed atomically:

1. **Task 1: Create template generation system prompt** - `980bbe0` (feat)
2. **Task 2: Add generate endpoint with validation and semaphore** - `20b6276` (feat)

## Files Created/Modified
- `src/agents/prompts/template_gen_system.txt` - System prompt for Claude CLI template generation
- `src/server/routers/templates.py` - Added generate endpoint, validation helper, Pydantic models, concurrency lock

## Decisions Made
- Used asyncio.Lock instead of Semaphore(1) -- simpler API, locked() method for non-blocking check
- Validation writes generated files to tempdir and runs existing loaders rather than custom validation
- System prompt kept concise at ~50 lines with no templating engine

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Generate endpoint ready for frontend integration
- Template editor (Phase 30) can use generated templates as starting point
- Validation errors surfaced in response for UI display

---
*Phase: 29-ai-template-generation*
*Completed: 2026-03-14*
