# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-03-12
**Phases:** 5 | **Plans:** 16

### What Was Built
- SQLite persistence layer with streaming NDJSON parser and retry-resilient Claude CLI runner
- 3-agent pipeline (Plan/Execute/Review) with structured handoffs and config-driven registry
- 4-panel Textual TUI with keyboard navigation, dark theme, and real-time streaming
- AI-driven orchestrator using Claude CLI JSON schema for autonomous agent routing
- Git auto-commit, token/cost tracking, resizable panels, and session history browser

### What Worked
- Bottom-up build order (infra → agents → TUI → orchestrator → polish) avoided rework
- TDD pattern in all plans caught integration issues early (160 tests passing)
- Textual framework's widget system (DataTable, ModalScreen, RichLog) mapped well to requirements
- asyncio.Event bridge pattern cleanly solved modal-to-async communication
- Config-driven agent registry made adding new agents trivial

### What Was Inefficient
- Agent output contract validation (AGNT-01/02/03) was designed but never enforced — shipped without
- Some ROADMAP.md plan checkboxes fell out of sync during rapid execution
- Phase 2 and 3 gap-closure plans were needed for wiring that should have been in original plans

### Patterns Established
- `stream_claude` yields mixed types (str for text, dict for metadata) — isinstance check pattern
- `asyncio.Event` bridge for awaiting Textual ModalScreen results from worker threads
- Separate `actions.py` module for TUI-pipeline decoupling and testability
- `auto_commit` with asyncio.Lock to prevent concurrent git operations
- `SessionBrowser` receives pre-loaded data via async worker before push_screen

### Key Lessons
1. Wire integrations in the same plan that creates the components — gap-closure plans are avoidable overhead
2. Textual's `run_test()` enables headless testing but requires careful async lifecycle management
3. Claude CLI `--json-schema` flag produces reliable structured output — prefer over text parsing
4. Output contracts via system prompts work for generation but need post-validation for enforcement

### Cost Observations
- Model mix: quality profile used throughout (opus for execution)
- Average plan execution: ~4 minutes
- Total execution: ~1 hour across 16 plans
- Notable: Parallel wave execution (2 agents simultaneously) cut Phase 5 wall time by ~40%

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 5 | 16 | Initial build — bottom-up with TDD |

### Cumulative Quality

| Milestone | Tests | Zero-Dep Additions |
|-----------|-------|--------------------|
| v1.0 | 160 | 0 (no external deps beyond Textual, aiosqlite) |

### Top Lessons (Verified Across Milestones)

1. Bottom-up build order with clear phase boundaries minimizes rework
2. TDD in every plan catches integration issues early and builds confidence for parallel execution
