---
phase: 26-agent-loader-foundation
plan: 01
subsystem: agents
tags: [frontmatter, yaml, agent-discovery, dataclass, python-frontmatter]

requires: []
provides:
  - "discover_project_agents() function for scanning .claude/agents/*.md"
  - "Extended AgentConfig with system_prompt_inline, source, file_path fields"
  - "python-frontmatter dependency for YAML parsing"
affects: [26-02, 27-registry-merge, 28-pipeline-integration]

tech-stack:
  added: [python-frontmatter==1.1.0]
  patterns: [frozen-dataclass-extension, frontmatter-parsing, filename-sanitization]

key-files:
  created:
    - src/agents/loader.py
    - tests/test_agent_loader.py
  modified:
    - src/agents/config.py
    - requirements.txt
    - tests/test_agent_config.py

key-decisions:
  - "Broad default transitions for project agents (plan, execute, test, review, approved)"
  - "Empty system_prompt_file string for project agents (they use inline prompts)"

patterns-established:
  - "Project agents use system_prompt_inline instead of system_prompt_file"
  - "Agent names sanitized: lowercase, spaces to hyphens, non-alphanumeric stripped"

requirements-completed: [AGLD-01, AGLD-02]

duration: 4min
completed: 2026-03-14
---

# Phase 26 Plan 01: Agent Loader Foundation Summary

**Agent discovery module with frontmatter parsing via python-frontmatter, extending AgentConfig for project-defined agents**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-14T17:20:40Z
- **Completed:** 2026-03-14T17:24:13Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Extended AgentConfig frozen dataclass with 3 new optional fields (system_prompt_inline, source, file_path) -- fully backward-compatible
- Created discover_project_agents() that scans .claude/agents/*.md and returns AgentConfig dict
- Handles both YAML-frontmatter and plain-text .md files with sensible defaults
- Skips empty/broken files gracefully with warning logs
- 12 new tests total (4 for config extension, 8 for loader)

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend AgentConfig and add python-frontmatter dependency** - `8c246b6` (feat)
2. **Task 2: Create agent loader with discovery and parsing** - `5fe989a` (feat)

_Note: Both tasks followed TDD (red-green) flow_

## Files Created/Modified
- `src/agents/config.py` - Added system_prompt_inline, source, file_path fields to AgentConfig
- `src/agents/loader.py` - New module: discover_project_agents(), _parse_agent_md(), _sanitize_name()
- `requirements.txt` - Added python-frontmatter==1.1.0
- `tests/test_agent_config.py` - 4 new tests for extended fields
- `tests/test_agent_loader.py` - 8 new tests for discovery and parsing

## Decisions Made
- Broad default transitions (plan, execute, test, review, approved) for project agents without explicit frontmatter
- Empty string for system_prompt_file on project agents since they use inline prompts
- Name sanitization: lowercase + hyphens only, strip special chars

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-existing test failures in test_agent_config.py (test_execute_config_sections, test_resolve_pipeline_order_default, test_resolve_pipeline_order_from_execute) due to execute.next_agent being "test" not "review" -- out of scope, not caused by our changes

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- AgentConfig extended and loader ready for Plan 02 (registry merge)
- discover_project_agents() returns clean AgentConfig dict ready for merging into AGENT_REGISTRY

---
*Phase: 26-agent-loader-foundation*
*Completed: 2026-03-14*
