---
phase: 01-foundation
plan: "02"
subsystem: infra
tags: [asyncio, subprocess, regex, ndjson, claude-cli]

# Dependency graph
requires:
  - phase: 01-foundation-01
    provides: test scaffolding with stubs and conftest fixtures
provides:
  - ClaudeRunner async generator (stream_claude, collect_claude)
  - extract_sections output parser with bold markdown support
affects: [02-agents, 03-tui, 04-orchestrator]

# Tech tracking
tech-stack:
  added: []
  patterns: [async-for stdout drain before wait, NDJSON line parsing, regex section extraction]

key-files:
  created:
    - src/__init__.py
    - src/runner/__init__.py
    - src/runner/runner.py
    - src/parser/__init__.py
    - src/parser/extractor.py
  modified:
    - tests/test_runner.py
    - tests/test_parser.py

key-decisions:
  - "Fixed SECTION_RE regex to use literal space instead of \\s to prevent cross-line matching"
  - "Fixed SECTION_RE regex to handle colon inside bold markers (**Goal:**)"

patterns-established:
  - "Deadlock-safe subprocess: async-for stdout drain before proc.wait()"
  - "NDJSON parsing: skip non-JSON lines with warning, extract text from assistant message blocks"
  - "Section extraction: regex with bold markdown normalization, fallback to CONTENT key"

requirements-completed: [INFR-01]

# Metrics
duration: 2min
completed: 2026-03-12
---

# Phase 1 Plan 02: Runner and Parser Summary

**Deadlock-safe async Claude CLI runner with NDJSON text extraction, and regex-based section parser with bold markdown support**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-12T06:17:47Z
- **Completed:** 2026-03-12T06:20:11Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Async subprocess runner that streams Claude CLI output with deadlock-safe stdout drain pattern
- NDJSON parser extracts text from assistant message blocks, skips non-JSON lines
- Section extractor handles uppercase, title-case, and **bold:** markdown headers
- Falls back to {"CONTENT": text} when no sections found
- All 6 live tests pass, 9 stubs remain skipped

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement ClaudeRunner and stream_claude async generator** - `75b80aa` (feat)
2. **Task 2: Implement extract_sections output parser** - `de85393` (feat)

_Note: TDD tasks used RED-GREEN flow (tests written first, then implementation)_

## Files Created/Modified
- `src/__init__.py` - Package init
- `src/runner/__init__.py` - Runner package init
- `src/runner/runner.py` - ClaudeRunner async generator with stream_claude and collect_claude
- `src/parser/__init__.py` - Parser package init
- `src/parser/extractor.py` - extract_sections with regex and fallback
- `tests/test_runner.py` - 2 live tests + 2 skipped retry stubs
- `tests/test_parser.py` - 4 live tests for section extraction

## Decisions Made
- Fixed SECTION_RE regex: replaced `\s` with literal space in character class to prevent cross-line matching (the `\s` shorthand matches newlines in MULTILINE mode, causing "Build something\n\nTASKS" to match as a single header)
- Fixed SECTION_RE regex: added `\*{0,2}` after the colon to handle bold markdown format `**Goal:**` where the colon appears inside the bold markers

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed SECTION_RE cross-line matching**
- **Found during:** Task 2 (extract_sections implementation)
- **Issue:** Plan's regex `[A-Za-z\s]+?` used `\s` which matches newlines in MULTILINE mode, causing multi-line text to match as headers
- **Fix:** Changed `\s` to literal space ` ` in character class
- **Files modified:** src/parser/extractor.py
- **Verification:** test_extract_sections_well_formed passes
- **Committed in:** de85393

**2. [Rule 1 - Bug] Fixed bold markdown colon position**
- **Found during:** Task 2 (extract_sections implementation)
- **Issue:** Regex expected `**header**:` but actual markdown format is `**header:**` (colon inside bold markers)
- **Fix:** Added `\*{0,2}` after the colon in regex: `:\*{0,2}\s*$`
- **Files modified:** src/parser/extractor.py
- **Verification:** test_extract_sections_bold_markdown_headers passes
- **Committed in:** de85393

---

**Total deviations:** 2 auto-fixed (2 bugs in research regex pattern)
**Impact on plan:** Both fixes necessary for correctness. No scope creep.

## Issues Encountered
None beyond the regex fixes documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Runner ready for retry wrapper (plan 03) and agent integration (phase 2)
- Parser ready for agent output processing (phase 2)
- All exports (stream_claude, collect_claude, extract_sections) available for import

---
*Phase: 01-foundation*
*Completed: 2026-03-12*
