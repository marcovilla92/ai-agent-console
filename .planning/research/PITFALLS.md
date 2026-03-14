# Domain Pitfalls

**Domain:** Adding file writing, bounded context, test agent, dynamic routing, and confidence gating to existing multi-agent orchestration pipeline
**Researched:** 2026-03-14
**Confidence:** HIGH (based on direct codebase analysis of orchestrator.py, context.py, runner.py, config.py, handoff.py, extractor.py, autocommit.py)

---

## Critical Pitfalls

### Pitfall 1: File Writer Parses Code Blocks But Execute Agent Output Format Is Not Enforced

**What goes wrong:** The file writer needs to extract file paths and code from the EXECUTE agent's output. The plan is to parse patterns like `` ```python # src/main.py ``. But `extract_sections()` in `src/parser/extractor.py` uses a regex (`SECTION_RE`) that matches section headers like `CODE:` -- it does not parse individual code blocks within a section. The CODE section content is a single blob of text. If the EXECUTE agent outputs code blocks with inconsistent path formats (`# src/main.py` vs `// File: src/main.py` vs `src/main.py:` vs no path at all), the file writer silently writes nothing or writes a single mega-file.

**Why it happens:**
- The EXECUTE agent's system prompt (`execute_system.txt`) requests structured output sections but does not enforce a specific code block format with file paths
- Claude LLMs vary their code block annotation style between runs -- sometimes `# filename`, sometimes a comment in the language, sometimes a markdown header before the block
- The parser works at the section level (CODE:, HANDOFF:, etc.) not at the code-block-within-section level
- Developers test with a single file output and miss the multi-file parsing edge case

**Consequences:** Pipeline completes, orchestrator approves, auto-commit runs -- but no files exist on disk. The git commit is empty. The user sees "approved" but nothing was written.

**Prevention:**
1. Update `execute_system.txt` to enforce a strict format: every code block MUST start with ```` ```language:path/to/file ```` (colon-separated language and path on the fence line). This is the most reliable LLM-parseable format.
2. Build the file writer parser with multiple fallback patterns in priority order: (a) ```` ```lang:path ```` fence, (b) `# path` comment on first line of block, (c) section header before block. Log which pattern matched.
3. Add a validation step: if file writer extracts zero files from a non-empty CODE section, log an error and report it back to the orchestrator as a failure -- do NOT silently approve.
4. Write a dedicated test with 5+ real EXECUTE agent outputs (capture them from actual runs) to validate the parser handles real-world format variation.

**Detection:** After implementing the file writer, run the pipeline end-to-end and check: does `git diff --stat` show actual file changes after the execute phase? If not, the parser is not matching.

**Phase to address:** File writer phase (improvement #1). The system prompt update and the parser must ship together -- parser without prompt update will fail on format variation.

---

### Pitfall 2: Bounded Handoff Windowing Breaks Re-Route Context

**What goes wrong:** The improvement plan says "keep only the last complete cycle (plan+execute+review)" and "cap total handoff size at 8000 chars". But `orchestrator.py:224-226` builds `agent_prompt` by joining ALL `state.accumulated_handoffs`. If you truncate to only the last cycle, a re-routed execute agent loses the original plan context from cycle 1. The execute agent receives: original user prompt + last review's issues -- but NOT the plan that established the architecture, file structure, and task breakdown. The execute agent makes contradictory decisions because it has no memory of the agreed plan.

**Why it happens:**
- The handoff list is flat (`list[str]`) with no metadata about which cycle or agent produced each entry
- "Last cycle" is ambiguous: does plan+execute+review count as one cycle, or is each agent invocation a cycle?
- The iteration counter (`state.iteration_count`) increments only after review, so mid-cycle you cannot determine cycle boundaries from the counter alone
- The plan handoff is the most critical context for execute, but it is also the oldest and first to be dropped by "keep last N" windowing

**Consequences:** Execute agent on re-route produces code that contradicts the original plan -- different file structure, different approach, missing components. Review flags new issues. The pipeline loops until the 3-iteration limit.

**Prevention:**
1. Always keep the FIRST plan handoff as a pinned prefix (never drop it). Window only subsequent handoffs.
2. Tag each handoff with `(agent_name, cycle_number)` metadata so windowing can be cycle-aware: keep the original plan + last complete cycle.
3. Implement the 8000 char cap as a soft limit on the windowed portion -- the pinned plan is exempt from the cap (but separately capped at 2000 chars with its own truncation).
4. Structure: `agent_prompt = original_prompt + pinned_plan_handoff + last_cycle_handoffs + targeted_issues`

**Detection:** Run a pipeline that goes through 2+ review cycles. Check the execute agent's prompt on cycle 2: does it contain the original plan's ARCHITECTURE and FILES TO CREATE sections? If not, windowing is too aggressive.

**Phase to address:** Bounded handoffs phase (improvement #3). Must be designed together with targeted re-route prompts (improvement #2) since both modify how agent_prompt is assembled.

---

### Pitfall 3: Dynamic Schema Generation Creates Invalid Enum When Test Agent Is Added

**What goes wrong:** Improvement #8 generates the orchestrator JSON schema enum dynamically from `AGENT_REGISTRY.keys()`. Improvement #6 adds "test" to the registry. The generated enum becomes `["plan", "execute", "review", "test", "approved"]`. But the orchestrator system prompt and the decision logic in `orchestrator.py:288` only handle `plan`, `execute`, and `approved` as re-route targets after review. If the orchestrator returns `{"next_agent": "test"}` when the current agent is `review`, the code falls through to the else branch (line 314: "Normal forward progression") and sets `current_agent = "test"` -- but there is no logic to handle test-to-review progression, and the test agent may re-run indefinitely if the orchestrator keeps routing back to test.

**Why it happens:**
- The schema enum and the decision handling logic are not co-located -- the enum is in `ORCHESTRATOR_SCHEMA` (line 59) and the routing logic is in the while loop (line 219)
- Adding an agent to the registry does not automatically add routing rules for it
- The `next_agent` field in `AgentConfig` defines a linear chain (execute->test->review) but the orchestrator's decision handler only knows about the special cases (approved, plan/execute after review)
- The text fallback parser (`parse_decision_from_text`) has no case for "test" -- it would default to "review"

**Consequences:** Orchestrator routes to test agent at unexpected times. Test agent runs after plan (nonsensical). Or test agent loops: test->orchestrator->test->orchestrator because the orchestrator has no rule saying "after test, go to review."

**Prevention:**
1. When generating the dynamic enum, also generate the valid transitions as a constraint. Define allowed transitions per agent: `{"plan": ["execute"], "execute": ["test", "review"], "test": ["review", "execute"], "review": ["plan", "execute", "approved"]}`.
2. Add a validation step after parsing the orchestrator decision: if `decision.next_agent` is not in the allowed transitions for `state.current_agent`, log a warning and use the `AgentConfig.next_agent` chain as fallback.
3. Update the orchestrator system prompt to explicitly list valid transitions, not just available agents: "After EXECUTE, you may route to TEST or REVIEW. After TEST, you may route to REVIEW or back to EXECUTE."
4. Update `parse_decision_from_text` to handle new agent names -- add "BACK TO TEST" pattern.

**Detection:** After adding the test agent, run a pipeline where the review says "needs fixes." Check: does the orchestrator ever route directly to "test" from "review"? That would skip execute and is likely wrong.

**Phase to address:** Test agent phase (improvement #6) and dynamic schema phase (improvement #8) must be coordinated. Add the test agent to the registry AND update the transition rules in the same phase.

---

### Pitfall 4: File Writer Runs After Execute But Before Review -- Writes Potentially Broken Code to Disk

**What goes wrong:** The improvement doc says "trigger write after execute completes" in `orchestrator.py`. But the review agent has not yet validated the code. If the file writer writes execute output to disk, and review finds critical issues (wrong architecture, security bugs, syntax errors), those broken files are now on the filesystem. The auto-commit logic (`autocommit.py`) only runs after "approved" -- but if the workspace is a live project (e.g., the ai-agent-console itself), writing broken files mid-pipeline can break the running server.

**Why it happens:**
- The natural insertion point is after `ctx.stream_output()` returns for execute -- this is where the output is freshly available
- The improvement doc focuses on "parse EXECUTE output and write files" without considering the review gate
- In autonomous mode, the pipeline moves fast -- execute writes files, review reads them, orchestrator approves -- but if review sends back to execute, the first iteration's files are already on disk and may conflict with the second iteration's files

**Consequences:** Broken code on disk between execute and review. If the project is the running server, it may crash. If auto-commit were to run mid-pipeline (it doesn't currently, but future changes might), broken code gets committed. On re-route iterations, old files from iteration 1 remain on disk unless explicitly cleaned up.

**Prevention:**
1. Write files to a staging area first (e.g., `.agent-staging/` within the project), not directly to the project root. Only copy from staging to project root after review approves.
2. OR: Accept the risk (simpler) but add a guard: only write files if the project path is NOT the ai-agent-console itself (the running server). For external projects, broken intermediate files are acceptable because git provides recovery.
3. On re-route iterations, the file writer must overwrite ALL files from the new execute output, not merge with the previous iteration's files. Clear the staging area before each execute write.
4. The auto-commit at the end of `orchestrate_pipeline` (line 320) must commit the FINAL state, not intermediate states. This is already correct in the current code -- but verify it stays that way.

**Detection:** Run a pipeline on a live project. After execute completes but before review, check: are there files on disk from execute? Are they syntactically valid? If you kill the pipeline mid-review, are broken files left on disk?

**Phase to address:** File writer phase (improvement #1). Decision: staging area vs direct write should be made before implementation begins. Direct write is simpler and acceptable given git recovery -- but document the decision explicitly.

---

### Pitfall 5: `stream_output()` Does Not Pass System Prompt File -- All Agents Run Without Their System Prompts

**What goes wrong:** Looking at `context.py:85`, `stream_output()` calls `stream_claude(prompt)` but does NOT pass the `system_prompt_file` parameter. The `stream_claude` function in `runner.py:36` accepts `system_prompt_file` as an optional kwarg, but `stream_output` never provides it. This means ALL agents (plan, execute, review) currently run without their system prompts. The system prompts exist in `src/agents/prompts/*.txt` and are referenced in `AGENT_REGISTRY`, but they are never used in the web execution path.

**Why it happens:**
- The `BaseAgent.run()` method (the TUI code path in `base.py:47`) correctly passes `system_prompt_file=self.config.system_prompt_file` to `invoke_claude_with_retry`
- When the web engine (`WebTaskContext.stream_output`) was built for v2.0, it called `stream_claude` directly without looking up the agent config
- The `stream_output` method signature takes `agent_name` as a string but never uses it to look up the `AgentConfig` for the system prompt path
- The agents still produce structured output because the prompt itself contains enough context -- but they are not constrained by the system prompt's formatting rules

**Consequences:** Agent outputs are less structured and less predictable. The orchestrator's section filtering (improvement #5) fails because sections are not consistently produced. The file writer's parsing fails because the execute agent does not follow the CODE section format. The review agent does not follow the DECISION section format. Everything appears to work in basic testing but degrades on complex tasks.

**Prevention:**
1. Fix `stream_output` to look up the agent's system prompt: `config = get_agent_config(agent_name); await stream_claude(prompt, system_prompt_file=config.system_prompt_file)`
2. This is a pre-existing bug that should be fixed BEFORE any v2.3 improvements, because all improvements depend on structured agent output
3. Add a log line in `stream_output` that logs which system prompt file is being used -- makes debugging easier
4. Add a test that verifies `stream_claude` is called with the correct system_prompt_file for each agent type

**Detection:** Check the Claude CLI process arguments in the Docker container logs. If `--system-prompt-file` is absent from agent calls (not just orchestrator calls), this bug is present.

**Phase to address:** This is a prerequisite fix. Address it as the FIRST task in v2.3, before any other improvement. Without system prompts, structured output is unreliable, and improvements #1, #2, #5, #6 all depend on structured output.

---

## Moderate Pitfalls

### Pitfall 6: Targeted Re-Route Prompt Extraction Depends on Section Names That Vary

**What goes wrong:** Improvement #2 extracts ISSUES and IMPROVEMENTS sections from review output to build targeted re-route prompts. But `extract_sections()` matches headers case-insensitively and normalizes to uppercase. If the review agent outputs "Issues Found:" vs "ISSUES:" vs "**Issues:**", all become "ISSUES FOUND" vs "ISSUES" vs "ISSUES" respectively. The re-route builder looks for `sections.get("ISSUES")` but gets `None` because the actual key is "ISSUES FOUND".

**Prevention:**
1. Use fuzzy matching for section lookup: check for keys containing "ISSUE" rather than exact match on "ISSUES"
2. Alternatively, add all expected variants to the review system prompt and enforce exact names
3. Build the re-route prompt from ANY section that is not SUMMARY or DECISION -- this catches ISSUES, IMPROVEMENTS, RISKS, and any unexpected section names

---

### Pitfall 7: Confidence Threshold Creates Approval Gate Confusion in Autonomous Mode

**What goes wrong:** Improvement #7 adds confidence-based gating: confidence < 0.5 asks for user confirmation even in autonomous mode. But `confirm_reroute()` in `context.py:173` auto-approves in non-supervised mode. If the confidence check triggers a confirmation request in autonomous mode, the `_wait_for_approval` method broadcasts an `approval_required` WebSocket event -- but the frontend may not have UI for unexpected approval gates in autonomous mode. The task hangs waiting for user input that the user does not expect.

**Prevention:**
1. Confidence-based gating should NOT use the same `confirm_reroute` / `_wait_for_approval` mechanism. Instead, it should log a warning and proceed in autonomous mode, or switch the task to supervised mode with a WebSocket notification explaining why.
2. Add a distinct WebSocket event type for low-confidence decisions (`low_confidence_warning`) separate from `approval_required`
3. Define the behavior clearly: autonomous mode NEVER blocks. Low confidence in autonomous mode = log warning + proceed. Low confidence in supervised mode = require approval.

---

### Pitfall 8: Adding Test Agent to Pipeline Doubles Claude CLI Invocations and Cost

**What goes wrong:** The current pipeline runs 3 agents per cycle (plan + execute + review) plus 1 orchestrator call after each = 6 Claude CLI invocations minimum. Adding a test agent between execute and review adds 2 more calls per cycle (test agent + orchestrator decision after test) = 8 calls per cycle. With the 2-concurrent-process semaphore and 7.6GB RAM constraint, the pipeline takes 33% longer. On re-route iterations (3 max), total calls go from 18 to 24.

**Prevention:**
1. The test agent should be a lightweight static reviewer -- NOT a full Claude CLI invocation. Use a simpler analysis: run `python -m py_compile` or `ruff check` on the written files and format results as a handoff. Only escalate to Claude CLI if static checks fail and need interpretation.
2. If the test agent must use Claude CLI, make it share the execute agent's system prompt with a test-specific addendum -- reducing prompt size and cost.
3. Track cost per pipeline run and set an alert if single-task cost exceeds $0.50

---

### Pitfall 9: Handoff Size Cap Silently Truncates Critical Information

**What goes wrong:** The 8000 char cap on bounded handoffs (`improvement #3`) truncates by slicing: `handoff_context[:8000]`. If a handoff ends mid-sentence or mid-code-block, the receiving agent gets malformed context. Worse, the truncation point might fall inside a JSON structure or a file path, causing the agent to misinterpret the context.

**Prevention:**
1. Truncate at section boundaries, not character boundaries. Find the last complete `=== END HANDOFF ===` marker before the 8000 char limit.
2. If individual handoffs exceed the cap, summarize them (extract only HANDOFF sections, drop CODE sections) rather than hard-truncating.
3. Log when truncation occurs, including how many characters were dropped -- this helps debug quality issues.

---

### Pitfall 10: Dynamic Schema Generation Exposes Internal Agent Names to Claude CLI

**What goes wrong:** Generating the enum from `AGENT_REGISTRY.keys()` means internal implementation names ("plan", "execute", "review", "test") become the values Claude must output. If someone renames an agent key in the registry (e.g., "execute" to "implement"), the orchestrator schema changes, the system prompt references change, and all hardcoded string comparisons in `orchestrator.py` break (`decision.next_agent == "execute"` no longer matches).

**Prevention:**
1. When building the dynamic enum, also generate all string comparisons from the registry. Use constants: `EXECUTE_AGENT = "execute"` and reference the constant everywhere.
2. Or: keep the schema enum values stable (always "plan", "execute", "review", "test", "approved") and only dynamically validate that each enum value has a corresponding registry entry at startup.
3. Add a startup validation: `assert set(ORCHESTRATOR_SCHEMA_ENUM) - {"approved"} == set(AGENT_REGISTRY.keys())`

---

## Minor Pitfalls

### Pitfall 11: File Writer Creates Directories But Does Not Handle Permission Errors

**What goes wrong:** `os.makedirs(parent, exist_ok=True)` fails with `PermissionError` if the project path is inside a read-only Docker volume mount or a directory owned by a different user.

**Prevention:** Wrap directory creation in try/except, log the specific path that failed, and surface the error to the user via WebSocket status update rather than silently failing.

---

### Pitfall 12: Orchestrator System Prompt Fix (Improvement #4) May Change Routing Behavior

**What goes wrong:** The orchestrator has been making decisions WITHOUT its system prompt for the entire lifetime of the web app (see Pitfall 5 for agents, and the improvement doc confirms the same for the orchestrator call). Adding the system prompt now may change routing behavior -- decisions that previously approved may now re-route, or vice versa. The system prompt may be stale or contain rules that conflict with the current pipeline behavior.

**Prevention:**
1. Review `orchestrator_system.txt` content before enabling it. Ensure it matches the current pipeline reality (3 agents, not 4).
2. Run the same test prompts with and without the system prompt and compare decisions. Log the before/after difference.
3. Enable the system prompt as a separate, isolated change so behavior differences are attributable to this single change.

---

### Pitfall 13: Git Auto-Commit Only Stages `src/` and `tests/` -- File Writer May Write to Other Directories

**What goes wrong:** `autocommit.py:34` only runs `git add` on `src/` and `tests/` patterns. If the file writer writes files to other directories (e.g., `config/`, `docs/`, `scripts/`, root-level files like `Dockerfile`), those files are never staged and never committed. The user sees "committed" but the new files are untracked.

**Prevention:**
1. After the file writer runs, collect the list of files it wrote. Pass this list to `auto_commit` and stage those specific files instead of using hardcoded patterns.
2. Or: change auto-commit to `git add` all files the file writer created, using `git add <file1> <file2> ...` with the explicit file list.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| File writer | Parser finds zero files in CODE section (Pitfall 1) | Enforce strict code block format in execute system prompt; test with real outputs |
| File writer | Writes broken code before review (Pitfall 4) | Accept direct-write with git recovery OR use staging area; document decision |
| File writer | Auto-commit misses non-src files (Pitfall 13) | Pass written file list to auto-commit |
| Targeted re-route | Section names vary (Pitfall 6) | Use fuzzy matching or "any section not SUMMARY/DECISION" |
| Bounded handoffs | Drops original plan context (Pitfall 2) | Pin first plan handoff; window only subsequent cycles |
| Bounded handoffs | Truncates mid-content (Pitfall 9) | Truncate at section boundaries, not character boundaries |
| System prompt fix | Changes routing behavior (Pitfall 12) | Review prompt content; compare before/after decisions |
| Section filtering | Depends on consistent section names (Pitfall 6) | Validate section names exist before filtering |
| Test agent | Doubles pipeline cost (Pitfall 8) | Use static analysis first, Claude CLI only as fallback |
| Test agent | Invalid transitions (Pitfall 3) | Define allowed transitions per agent; validate decisions |
| Confidence gating | Blocks autonomous mode unexpectedly (Pitfall 7) | Never block in autonomous mode; log + proceed |
| Dynamic schema | Enum includes agents without routing rules (Pitfall 3) | Generate transitions alongside enum |
| Dynamic schema | Internal names leaked as contract (Pitfall 10) | Use constants; validate enum matches registry at startup |
| ALL improvements | Agents run without system prompts (Pitfall 5) | FIX THIS FIRST -- prerequisite for all other improvements |

---

## "Looks Done But Isn't" Checklist

- [ ] **System prompts actually used:** Check Docker logs for `--system-prompt-file` flag in Claude CLI process arguments for ALL agent calls (not just orchestrator)
- [ ] **File writer produces files:** After a full pipeline run, `git diff --stat` shows actual file changes in the project directory
- [ ] **Re-route keeps plan context:** On iteration 2+, the execute agent's prompt contains the original plan's ARCHITECTURE section
- [ ] **Handoff truncation is clean:** No handoff ends mid-word or mid-code-block after the 8000 char cap
- [ ] **Test agent does not loop:** Pipeline with test agent completes in <= 3 iterations without test->test cycling
- [ ] **Confidence does not block autonomous:** An autonomous task with confidence=0.4 proceeds (with warning log) rather than hanging
- [ ] **Dynamic schema matches registry:** Adding a new agent to AGENT_REGISTRY automatically appears in the orchestrator schema enum AND the system prompt
- [ ] **Auto-commit includes all written files:** Files written to `config/`, `docs/`, or root directory are staged and committed, not just `src/` and `tests/`
- [ ] **Old tests still pass:** `pytest tests/ -x` passes after each improvement phase, not just at the end

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| File writer produces no files | LOW | Check parser patterns; capture raw EXECUTE output from DB; test parser against it; fix patterns |
| Bounded handoffs drop plan context | MEDIUM | Revert to full handoff concatenation (old behavior); redesign windowing with pinned plan |
| Test agent routing loops | LOW | Remove test from AGENT_REGISTRY; revert to plan->execute->review chain; redesign transitions |
| Autonomous mode blocks on confidence | LOW | Change confidence check to log-only in autonomous mode; redeploy |
| System prompt changes routing | LOW | Remove `--system-prompt-file` from orchestrator call; revert to promptless behavior; review prompt content |
| Auto-commit misses files | LOW | Run `git add` on the specific files manually; update auto-commit to accept file list |

---

## Sources

- Direct codebase analysis: `src/pipeline/orchestrator.py` (343 lines), `src/engine/context.py` (200 lines), `src/runner/runner.py` (197 lines), `src/agents/config.py` (79 lines), `src/pipeline/handoff.py` (38 lines), `src/parser/extractor.py` (47 lines), `src/git/autocommit.py` (80 lines), `src/agents/base.py` (74 lines)
- Improvement specification: `docs/orchestration-improvements.md` (8 improvements, prioritized)
- Project context: `.planning/PROJECT.md` (v2.3 milestone definition)

---
*Pitfalls research for: v2.3 Orchestration Improvements -- file writing, bounded context, test agent, dynamic routing*
*Researched: 2026-03-14*
