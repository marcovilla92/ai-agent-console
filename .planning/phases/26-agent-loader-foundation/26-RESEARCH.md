# Phase 26: Agent Loader Foundation - Research

**Researched:** 2026-03-14
**Domain:** Dynamic agent discovery, YAML frontmatter parsing, per-project registry isolation
**Confidence:** HIGH

## Summary

Phase 26 builds the foundational agent loading system that makes template-defined agents participate in the pipeline. Currently, `AGENT_REGISTRY` in `src/agents/config.py` is a hardcoded dict of 4 agents (plan, execute, test, review). Templates ship `.claude/agents/*.md` files (db-migrator, api-tester, handler-builder, command-builder) but these are never read by the runtime. This phase creates the loader, the merge logic, and the per-project registry isolation -- without yet modifying the orchestrator or context assembly (those are Phase 28 and Phase 27 respectively).

The critical design constraint is concurrency: the system supports 2 concurrent tasks via `asyncio.Semaphore(2)`. Both share the same Python process and module-level state. The registry MUST NOT be mutated globally. Instead, a shallow-copy merge pattern produces a per-task registry that is threaded through the call chain. The `AgentConfig` dataclass is `frozen=True`, which is good for immutability but requires adding new fields (`system_prompt_inline`, `source`, `file_path`) before the loader is written.

**Primary recommendation:** Add `python-frontmatter==1.1.0` as the only new dependency. Create `src/agents/loader.py` with `discover_project_agents()`. Extend `AgentConfig` with 3 new fields. Rename `AGENT_REGISTRY` to `DEFAULT_REGISTRY` (keep alias for backward compat). Add `get_project_registry()` and `merge_registries()` to `config.py`. Do NOT modify orchestrator or context assembly in this phase.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AGLD-01 | System auto-discovers all `.claude/agents/*.md` files in project directory | `discover_project_agents()` in new `src/agents/loader.py` using `pathlib.glob("*.md")` |
| AGLD-02 | System parses YAML frontmatter from agent MD with sensible defaults for plain-text files | `python-frontmatter==1.1.0` handles parsing; defaults: name from filename, description from "Project agent: {name}", broad transitions |
| AGLD-03 | System creates isolated per-project registry (merged copy, no global mutation) | `get_project_registry(project_path)` returns `{**DEFAULT_REGISTRY, **project_agents}` -- new dict per call |
| AGLD-04 | Core pipeline agents (plan/execute/test/review) cannot be overridden by project agent files | `PROTECTED_AGENTS` set in `merge_registries()` skips conflicts with warning log |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| python-frontmatter | 1.1.0 | Parse YAML frontmatter from `.md` files | Handles BOM, encoding edge cases, embedded `---` in YAML; transitive dep PyYAML already at 6.0.1 |
| pathlib | stdlib | Directory scanning for agent discovery | Already used throughout codebase |
| dataclasses | stdlib | Extended `AgentConfig` with new fields | Existing pattern, `frozen=True` preserved |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| logging | stdlib | Warning on skipped agents, parse errors | Per-file error reporting without crashes |
| re | stdlib | Filename sanitization | Agent name normalization from filenames |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| python-frontmatter | Manual `---` splitting + `yaml.safe_load` | Manual approach misses BOM handling, embedded `---` in values, empty files -- all edge cases the library handles. Library is 1 file, minimal overhead. |
| python-frontmatter | gray-matter (Node) | Wrong ecosystem. Python project. |

**Installation:**
```bash
pip install python-frontmatter==1.1.0
```

Add to `requirements.txt`:
```
python-frontmatter==1.1.0
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── agents/
│   ├── config.py        # MODIFY: add fields, DEFAULT_REGISTRY, get_project_registry, merge_registries
│   ├── loader.py        # NEW: discover_project_agents(), _parse_agent_md()
│   ├── base.py          # UNCHANGED
│   └── prompts/         # UNCHANGED
```

### Pattern 1: Discovery Module
**What:** Single-purpose module that scans a directory and returns structured data.
**When to use:** Any file-based plugin/extension discovery.
**Example:**
```python
# src/agents/loader.py
from pathlib import Path
import frontmatter

from src.agents.config import AgentConfig

CLAUDE_AGENTS_DIR = ".claude/agents"

def discover_project_agents(project_path: str) -> dict[str, AgentConfig]:
    """Scan .claude/agents/*.md and return dict of agent_name -> AgentConfig."""
    agents_dir = Path(project_path) / CLAUDE_AGENTS_DIR
    if not agents_dir.is_dir():
        return {}
    result = {}
    for md_file in sorted(agents_dir.glob("*.md")):
        try:
            config = _parse_agent_md(md_file)
            if config:
                result[config.name] = config
        except Exception:
            log.warning("Failed to parse agent file %s, skipping", md_file, exc_info=True)
    return result
```

### Pattern 2: Frontmatter Parse with Graceful Defaults
**What:** Parse optional YAML frontmatter, fall back to sensible defaults for plain-text files.
**When to use:** When loading user-authored markdown files that may or may not have metadata.
**Example:**
```python
def _parse_agent_md(md_path: Path) -> AgentConfig | None:
    """Parse a .claude/agents/*.md file into an AgentConfig."""
    content = md_path.read_text(encoding="utf-8", errors="replace")
    if not content.strip():
        log.warning("Empty agent file %s, skipping", md_path.name)
        return None

    name = _sanitize_name(md_path.stem)

    post = frontmatter.loads(content)
    meta = post.metadata  # dict (empty if no frontmatter)
    body = post.content    # str (full content if no frontmatter)

    return AgentConfig(
        name=meta.get("name", name),
        system_prompt_file="",  # project agents use inline, not file
        system_prompt_inline=body,
        description=meta.get("description", f"Project agent: {name}"),
        output_sections=meta.get("output_sections", []),
        next_agent=meta.get("next_agent"),
        allowed_transitions=tuple(meta.get("allowed_transitions",
            ("plan", "execute", "test", "review", "approved"))),
        source="project",
        file_path=str(md_path),
    )
```

### Pattern 3: Protected Merge with Shallow Copy
**What:** Merge two registries without mutating either, protecting core agents.
**When to use:** Combining defaults with project-specific extensions.
**Example:**
```python
PROTECTED_AGENTS = frozenset({"plan", "execute", "test", "review"})

def merge_registries(
    default: dict[str, AgentConfig],
    project: dict[str, AgentConfig],
) -> dict[str, AgentConfig]:
    """Merge project agents into default registry. Core agents are protected."""
    merged = dict(default)  # shallow copy
    for name, config in project.items():
        if name in PROTECTED_AGENTS:
            log.warning("Project agent '%s' conflicts with core agent, skipping", name)
            continue
        merged[name] = config
    return merged
```

### Anti-Patterns to Avoid
- **Global mutation:** Never do `AGENT_REGISTRY.update(project_agents)`. Creates cross-project contamination between concurrent tasks.
- **Subclassing AgentConfig:** Do not create `DynamicAgentConfig(AgentConfig)`. Adds type-checking complexity. Just add fields to the existing dataclass.
- **Temp file writing for inline prompts:** Do not write project agent prompts to temp files. The runner will eventually support `--system-prompt` for inline prompts (Phase 28). For now, store as `system_prompt_inline` field.
- **Async discovery:** Agent discovery is pure filesystem I/O on local disk. `pathlib.glob()` is fast enough (<5ms for 10 files). No need for async.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML frontmatter parsing | Custom `---` splitter + yaml.safe_load | `python-frontmatter` | Handles BOM, encoding errors, embedded delimiters, empty files |
| Agent name sanitization | Complex regex | Simple `stem.lower().replace(" ", "-")` with `re.sub(r"[^a-z0-9-]", "", ...)` | Agent names are filesystem-derived, limited character set |

**Key insight:** The loader is architecturally simple (scan + parse + merge). The complexity is in the integration points (orchestrator schema, context assembly) which are NOT in this phase.

## Common Pitfalls

### Pitfall 1: Frozen Dataclass Blocks Extension
**What goes wrong:** `AgentConfig` is `@dataclass(frozen=True)`. Adding `system_prompt_inline`, `source`, `file_path` after writing the loader forces a rewrite.
**Why it happens:** Frozen dataclasses reject any field addition after instantiation.
**How to avoid:** Add all 3 new fields to `AgentConfig` FIRST, before writing the loader. Fields must have defaults so existing code continues to work.
**Warning signs:** `TypeError: __init__() got an unexpected keyword argument` when creating project AgentConfigs.

### Pitfall 2: Name Collision with Reserved Names
**What goes wrong:** A project ships `plan.md` or `execute.md` in `.claude/agents/`. Without protection, these override core pipeline agents, breaking routing.
**Why it happens:** Filename-to-name mapping is mechanical; no validation against reserved names.
**How to avoid:** `PROTECTED_AGENTS` frozenset checked in `merge_registries()`. Log warning and skip.
**Warning signs:** Pipeline crashes after loading project with agent file named after a core agent.

### Pitfall 3: Markdown Parse Fragility
**What goes wrong:** Files with BOM characters, Windows line endings, binary content, or `---` in body text crash the parser.
**Why it happens:** Custom YAML frontmatter parsers don't handle edge cases.
**How to avoid:** Use `python-frontmatter` which handles all these. Wrap per-file in try/except, skip broken files with warning.
**Warning signs:** `UnicodeDecodeError`, `yaml.YAMLError` on otherwise valid-looking `.md` files.

### Pitfall 4: Agent Routing Dead Ends
**What goes wrong:** Project agents load with empty `allowed_transitions`. Orchestrator routes to them but they have no valid forward path. Fallback logic returns "approved", prematurely ending the pipeline.
**Why it happens:** Existing `.md` files are plain text with no frontmatter metadata.
**How to avoid:** Default `allowed_transitions` for project agents should be broad: `("plan", "execute", "test", "review", "approved")`. Let the orchestrator decide freely.
**Warning signs:** Pipeline ends prematurely after a single project agent run.

### Pitfall 5: `get_agent_config()` Breaks for Dynamic Agents
**What goes wrong:** `get_agent_config()` and `validate_transition()` read from the global `AGENT_REGISTRY`. They won't find project agents, returning `KeyError` or invalid fallbacks.
**Why it happens:** These functions are hardcoded to the global registry.
**How to avoid:** Add `registry` parameter to `build_agent_enum()`, `build_agent_descriptions()`, `validate_transition()`, and `get_agent_config()` with backward-compatible defaults. This phase adds the parameter; Phase 28 (orchestrator) threads it through the call chain.
**Warning signs:** `KeyError: "Unknown agent: 'db-migrator'"` during pipeline execution.

## Code Examples

### AgentConfig Extension (must be done first)
```python
# src/agents/config.py - Modified AgentConfig
@dataclass(frozen=True)
class AgentConfig:
    name: str
    system_prompt_file: str
    description: str = ""
    output_sections: list[str] = field(default_factory=list)
    next_agent: str | None = None
    allowed_transitions: tuple[str, ...] = ()
    # NEW fields for v2.4
    system_prompt_inline: str | None = None  # inline prompt for project agents
    source: str = "default"                   # "default" or "project"
    file_path: str | None = None              # path to source .md file
```

### Registry Refactor
```python
# src/agents/config.py - Registry pattern
DEFAULT_REGISTRY: dict[str, AgentConfig] = {
    "plan": AgentConfig(...),
    "execute": AgentConfig(...),
    "test": AgentConfig(...),
    "review": AgentConfig(...),
}
AGENT_REGISTRY = DEFAULT_REGISTRY  # backward compat alias

def get_project_registry(project_path: str | None = None) -> dict[str, AgentConfig]:
    """Build a scoped registry: defaults + project agents."""
    if not project_path:
        return dict(DEFAULT_REGISTRY)
    from src.agents.loader import discover_project_agents
    project_agents = discover_project_agents(project_path)
    return merge_registries(DEFAULT_REGISTRY, project_agents)
```

### Functions with Registry Parameter (backward compat)
```python
def build_agent_enum(registry: dict[str, AgentConfig] | None = None) -> list[str]:
    """Build valid routing targets. Accepts optional registry for dynamic agents."""
    reg = registry if registry is not None else AGENT_REGISTRY
    return sorted(list(reg.keys()) + ["approved"])

def build_agent_descriptions(registry: dict[str, AgentConfig] | None = None) -> str:
    """Build agent description block. Accepts optional registry for dynamic agents."""
    reg = registry if registry is not None else AGENT_REGISTRY
    lines = []
    for name, config in reg.items():
        desc = config.description or f"Agent: {name}"
        lines.append(f"- {name.upper()}: {desc}")
    return "\n".join(lines)

def validate_transition(from_agent: str, to_agent: str, registry: dict[str, AgentConfig] | None = None) -> str:
    """Validate a routing transition. Accepts optional registry for dynamic agents."""
    reg = registry if registry is not None else AGENT_REGISTRY
    if to_agent == "approved":
        return "approved"
    config = reg.get(from_agent)
    if not config:
        return to_agent
    if config.allowed_transitions and to_agent not in config.allowed_transitions:
        fallback = config.next_agent or "approved"
        log.warning("Invalid transition %s -> %s, falling back to %s", from_agent, to_agent, fallback)
        return fallback
    return to_agent

def get_agent_config(name: str, registry: dict[str, AgentConfig] | None = None) -> AgentConfig:
    """Get agent config by name. Accepts optional registry for dynamic agents."""
    reg = registry if registry is not None else AGENT_REGISTRY
    if name not in reg:
        raise KeyError(f"Unknown agent: {name!r}. Available: {list(reg)}")
    return reg[name]
```

### Agent Markdown Format (with frontmatter)
```markdown
---
name: db-migrator
description: Database migration specialist for PostgreSQL
allowed_transitions:
  - execute
  - review
  - approved
---

You are a database migration specialist for PostgreSQL with asyncpg.
Create idempotent SQL migrations...
```

### Agent Markdown Format (without frontmatter -- backward compat)
```markdown
You are a database migration specialist for PostgreSQL with asyncpg.
Create idempotent SQL migrations...
```
Loaded with defaults: name=`db-migrator` (from filename), description=`Project agent: db-migrator`, allowed_transitions=`(plan, execute, test, review, approved)`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded 4-agent registry | Dynamic per-project registry | This phase | Templates become "live" |
| Module-level constants for routing | Functions accepting registry parameter | This phase | Enables per-task schema in Phase 28 |
| No inline prompt support | `system_prompt_inline` field on AgentConfig | This phase | Project agents carry their own prompts |

**Deprecated/outdated:**
- `AGENT_REGISTRY` name: remains as backward-compat alias, but `DEFAULT_REGISTRY` is the canonical name going forward.

## Open Questions

1. **Existing template agent files migration**
   - What we know: All 4 existing template agent files (db-migrator, api-tester, handler-builder, command-builder) are plain text without frontmatter
   - What's unclear: Should we add frontmatter to these files now or leave them as-is?
   - Recommendation: Leave as-is. The loader handles plain-text files with sensible defaults. Migration can happen opportunistically later. Zero risk of breakage.

2. **`resolve_pipeline_order()` with dynamic agents**
   - What we know: This function walks the `next_agent` chain from the global registry
   - What's unclear: Whether it needs a registry parameter now or in Phase 28
   - Recommendation: Add the registry parameter now for consistency, but it is not critical since dynamic agents typically don't form linear chains.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio |
| Config file | `pytest.ini` (exists, `asyncio_mode = auto`) |
| Quick run command | `python -m pytest tests/test_agent_loader.py tests/test_agent_config.py -x` |
| Full suite command | `python -m pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AGLD-01 | Discover `.claude/agents/*.md` files | unit | `python -m pytest tests/test_agent_loader.py::test_discover_agents_from_directory -x` | Wave 0 |
| AGLD-01 | Return empty dict when no agents dir | unit | `python -m pytest tests/test_agent_loader.py::test_discover_no_agents_dir -x` | Wave 0 |
| AGLD-02 | Parse YAML frontmatter correctly | unit | `python -m pytest tests/test_agent_loader.py::test_parse_with_frontmatter -x` | Wave 0 |
| AGLD-02 | Parse plain-text files with sensible defaults | unit | `python -m pytest tests/test_agent_loader.py::test_parse_without_frontmatter -x` | Wave 0 |
| AGLD-02 | Skip broken/empty files gracefully | unit | `python -m pytest tests/test_agent_loader.py::test_skip_broken_files -x` | Wave 0 |
| AGLD-03 | Per-project registry is isolated copy | unit | `python -m pytest tests/test_agent_config.py::test_project_registry_is_isolated -x` | Wave 0 |
| AGLD-03 | Global DEFAULT_REGISTRY unmodified after merge | unit | `python -m pytest tests/test_agent_config.py::test_default_registry_unchanged -x` | Wave 0 |
| AGLD-04 | Core agents protected from override | unit | `python -m pytest tests/test_agent_config.py::test_core_agents_protected -x` | Wave 0 |
| AGLD-04 | Warning logged when core agent conflict | unit | `python -m pytest tests/test_agent_config.py::test_core_override_logs_warning -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_agent_loader.py tests/test_agent_config.py -x`
- **Per wave merge:** `python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_agent_loader.py` -- covers AGLD-01, AGLD-02 (new file)
- [ ] Updated `tests/test_agent_config.py` -- covers AGLD-03, AGLD-04 (existing file, add tests)
- [ ] `python-frontmatter==1.1.0` added to `requirements.txt`

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis: `src/agents/config.py` (149 lines), `src/agents/base.py` (74 lines), `src/pipeline/orchestrator.py` (454 lines), `src/engine/context.py` (217 lines), `src/engine/manager.py`, `src/context/assembler.py` (283 lines)
- Existing template agent files: `templates/fastapi-pg/.claude/agents/db-migrator.md`, `api-tester.md`; `templates/telegram-bot/.claude/agents/handler-builder.md`; `templates/cli-tool/.claude/agents/command-builder.md` -- all plain text, no frontmatter
- Existing test suite: `tests/test_agent_config.py` (76 lines) -- tests for registry, get_agent_config, resolve_pipeline_order
- Project-level research: `.planning/research/SUMMARY.md`, `ARCHITECTURE.md`, `PITFALLS.md` -- all HIGH confidence, direct codebase analysis
- Design document: `docs/template-system-overhaul.md` -- requirements R1-R5

### Secondary (MEDIUM confidence)
- `python-frontmatter` PyPI page -- version 1.1.0 confirmed as latest stable; transitive dep is PyYAML only

### Tertiary (LOW confidence)
- None. All findings are from direct codebase analysis.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - `python-frontmatter` verified, all other deps are stdlib or existing
- Architecture: HIGH - all affected files read line-by-line, call chain fully traced from `TaskManager._execute()` through `orchestrate_pipeline()` through `WebTaskContext.stream_output()` through `get_agent_config()`
- Pitfalls: HIGH - all derived from actual code paths, not speculation

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable domain, no external API dependencies)
