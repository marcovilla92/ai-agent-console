# Pitfalls Research

**Domain:** Terminal-based multi-agent AI orchestration console (TUI)
**Researched:** 2026-03-11
**Confidence:** HIGH (core subprocess/TUI patterns) to MEDIUM (Claude CLI-specific streaming behavior)

## Critical Pitfalls

### Pitfall 1: Subprocess Deadlocks from Unbuffered Stream Reading

**What goes wrong:**
The Claude CLI subprocess blocks because its stdout/stderr pipe buffer fills up. The Python side is waiting on `process.wait()` before reading output, creating a classic deadlock: the child waits for the parent to drain the buffer, the parent waits for the child to exit.

**Why it happens:**
Developers use `await process.wait()` or `process.communicate()` before consuming the stream, or they read stdout and stderr sequentially instead of concurrently. OS pipe buffers are typically 64KB -- a single Claude response easily exceeds this.

**How to avoid:**
- Use `asyncio.create_subprocess_exec` with `stdout=PIPE, stderr=PIPE`.
- Read stdout and stderr concurrently using `asyncio.gather` or `asyncio.TaskGroup`.
- Never call `process.wait()` before fully consuming both streams.
- For streaming display, use `async for line in process.stdout` which reads line-by-line without buffering the full output.
- Set timeouts with `asyncio.wait_for()` and terminate the process on timeout.

```python
# WRONG - deadlock risk
await process.wait()
output = await process.stdout.read()

# RIGHT - concurrent consumption
async def read_stream(stream, callback):
    async for line in stream:
        await callback(line.decode())

await asyncio.gather(
    read_stream(process.stdout, on_stdout),
    read_stream(process.stderr, on_stderr),
)
await process.wait()
```

**Warning signs:**
- TUI freezes during long Claude responses.
- Agent appears to hang but CPU usage is zero.
- Works with short prompts, fails with long outputs.

**Phase to address:**
Phase 1 (core subprocess infrastructure). This is foundational -- every agent depends on reliable subprocess communication.

---

### Pitfall 2: Structured Output Parsing Brittleness

**What goes wrong:**
The orchestrator depends on Claude returning well-formed structured output (GOAL, TASKS, ARCHITECTURE, etc.) via system prompts. Claude returns malformed output: extra conversational text wrapping the structure, missing sections, inconsistent field names, or partial JSON. The parser breaks, the orchestrator cannot determine the next action, and the pipeline halts.

**Why it happens:**
LLMs are non-deterministic. Even with excellent system prompts, output format compliance is approximately 94% at best. The remaining 6% includes: preamble text ("Sure, here's the plan:"), missing closing markers, hallucinated extra fields, or subtle format drift between runs. Using Claude CLI (not the API with JSON schema enforcement) means there is no server-side format guarantee.

**How to avoid:**
- Use `--output-format stream-json` with Claude CLI to get structured JSON-lines output, which provides more reliable framing than raw text parsing.
- Design a multi-layer parsing strategy: (1) try strict parse, (2) try lenient parse with regex fallback for known sections, (3) try JSON repair (e.g., `json_repair` library), (4) flag as unparseable and retry.
- Define explicit section markers that are easy to regex-match (e.g., `## GOAL`, `## TASKS`) rather than relying on JSON embedded in prose.
- Keep structured output contracts simple -- fewer fields means higher compliance.
- Validate parsed output against a schema before passing to orchestrator.
- Log every raw Claude response before parsing for debugging.

**Warning signs:**
- Intermittent "parse failed" errors that seem random.
- Output format works in testing but breaks in production with varied prompts.
- Different Claude model versions produce different format compliance rates.

**Phase to address:**
Phase 1-2. Build the parser with fallback layers from day one. Never assume 100% format compliance.

---

### Pitfall 3: Textual Event Loop Blocking from Synchronous Operations

**What goes wrong:**
The TUI freezes, becomes unresponsive to keyboard input, or visually stutters. The user cannot cancel a running agent, switch panels, or even quit the application during long-running operations.

**Why it happens:**
Textual runs on a single asyncio event loop. Any synchronous/blocking call in a message handler -- `subprocess.run()`, `time.sleep()`, synchronous file I/O, or even a slow SQLite query -- blocks the entire UI. Developers test with fast operations and miss that the same code path blocks under load.

**How to avoid:**
- Use Textual's `@work` decorator or `run_worker()` for ALL subprocess and I/O operations.
- Use `thread=True` for synchronous libraries (e.g., `sqlite3`) that cannot be made async.
- Never call `subprocess.run()` or `subprocess.Popen().wait()` in message handlers -- always use `asyncio.create_subprocess_exec` within a worker.
- Use `aiosqlite` instead of raw `sqlite3` for database access.
- Profile the event loop: if any single handler takes >50ms, it needs to be a worker.

**Warning signs:**
- TUI input lag during agent execution.
- Keyboard shortcuts stop responding mid-operation.
- "Application not responding" feel when switching panels.

**Phase to address:**
Phase 1. Establish the worker pattern for all I/O from the very first prototype. Retrofitting workers onto blocking code is painful.

---

### Pitfall 4: Orchestrator Infinite Loops and Runaway Agents

**What goes wrong:**
The AI-driven orchestrator calls REVIEW, which requests improvements, which triggers EXECUTE, which produces output that REVIEW again finds insufficient, creating an infinite improvement loop. Or the orchestrator misinterprets agent output and keeps retrying the same failing operation. Token costs spiral, the user waits forever, and no useful output is produced.

**Why it happens:**
An AI-driven orchestrator (vs. rule-based) makes non-deterministic routing decisions. Without explicit loop detection or iteration limits, the orchestrator can get stuck in cycles. The "prompting fallacy" -- believing better prompts alone can fix systemic coordination failures -- leads developers to tweak prompts instead of adding hard guardrails.

**How to avoid:**
- Implement hard iteration limits per cycle (e.g., max 3 REVIEW-EXECUTE loops before forcing user confirmation).
- Track orchestrator state machine transitions and detect cycles (same agent called >N times without state change).
- Require user confirmation for every REVIEW->EXECUTE iteration (the project already plans this -- enforce it strictly).
- Add a "cost budget" per session: total token usage cannot exceed a threshold without explicit user approval.
- Log every orchestrator decision with reasoning for post-hoc debugging.
- Define clear "done" criteria that the orchestrator can evaluate deterministically, not subjectively.

**Warning signs:**
- Same agent called 3+ times in a row.
- Total session tokens growing without proportional output.
- REVIEW agent repeatedly finding the same issues.

**Phase to address:**
Phase 2-3 (orchestrator implementation). Build cycle detection and hard limits before making the orchestrator AI-driven. Start with a rule-based orchestrator with human-in-the-loop, then add AI routing.

---

### Pitfall 5: Agent Context Window Exhaustion

**What goes wrong:**
As the pipeline progresses (PLAN -> EXECUTE -> REVIEW -> EXECUTE again), the accumulated context (original prompt + plan + code output + review feedback + previous iterations) exceeds Claude's context window. The agent starts losing critical information, produces contradictory output, or fails entirely.

**Why it happens:**
Developers pass the full conversation history to each agent. With code generation, a single EXECUTE cycle can produce 10-20KB of output. After 2-3 review iterations, the context easily exceeds practical limits. Even within the context window, LLM quality degrades with very long contexts ("lost in the middle" phenomenon).

**How to avoid:**
- Design each agent call as stateless with a focused context window: pass only what the agent needs, not the full history.
- Summarize previous outputs before passing to the next agent. The HANDOFF section in the output contract is exactly this -- make it the only thing passed forward, not the full output.
- Store full outputs in SQLite/files and pass references, not content.
- For REVIEW iterations: pass only the current code + specific review feedback, not the entire review history.
- Monitor token counts per agent call and warn when approaching 60% of context window.

**Warning signs:**
- Agent output quality degrades in later iterations.
- Agent "forgets" requirements stated in the original prompt.
- EXECUTE agent produces code that contradicts the PLAN after review iterations.

**Phase to address:**
Phase 2 (agent communication design). The context management strategy must be designed before building the iterative pipeline.

---

### Pitfall 6: Claude CLI stream-json Partial Message Handling

**What goes wrong:**
The TUI tries to display streaming output from Claude CLI using `--output-format stream-json`, but structured JSON output only appears in the final `result` message, not incrementally. The TUI shows nothing for seconds/minutes during generation, then dumps everything at once. Alternatively, partial text messages stream fine but the structured `result.structured_output` is null until completion.

**Why it happens:**
Claude CLI's `stream-json` format emits JSON-lines where each line is a complete JSON object. Text content streams as `assistant` message deltas, but `--json-schema` constrained output does NOT stream incrementally -- it appears only in the final result. This is a known limitation (GitHub issue #15511 on claude-code).

**How to avoid:**
- Do NOT rely on `--json-schema` for real-time streaming display. Use plain text output with section markers for the streaming display, then parse the completed output.
- Stream the text content to the TUI panel in real-time for user feedback.
- Parse the structured sections only after the agent completes.
- Design TUI to show "Agent thinking..." with streaming text preview, then parse+display structured output on completion.
- Handle both partial `assistant` messages (for display) and the final `result` message (for parsing) as separate concerns.

**Warning signs:**
- TUI panel stays blank during agent execution despite activity.
- Structured output appears only after long delays.
- Attempting to parse incomplete JSON-lines mid-stream causes errors.

**Phase to address:**
Phase 1 (streaming infrastructure). This design decision affects the entire display and parsing architecture.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Regex parsing instead of proper section parser | Quick to implement | Breaks on edge cases, impossible to maintain with format changes | MVP only -- replace in Phase 2 |
| Storing full agent output in memory instead of SQLite | Simpler architecture | Memory grows unbounded with iterations; crash loses everything | Never -- stream to SQLite from Phase 1 |
| Hardcoded agent prompts instead of template system | Faster initial development | Cannot tune prompts without code changes, no A/B testing | MVP only -- extract to config files in Phase 2 |
| Single SQLite connection without WAL mode | Works in development | Concurrent reads from UI thread + writes from worker thread cause "database locked" errors | Never -- enable WAL mode from day one |
| Passing raw subprocess output without sanitization | Less code | Terminal escape sequences in Claude output corrupt TUI rendering | Never -- strip/sanitize from Phase 1 |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Claude CLI subprocess | Using `subprocess.run()` (blocking) | Use `asyncio.create_subprocess_exec` with stream reading in a Textual worker |
| Claude CLI `--dangerously-skip-permissions` | Assuming it always works silently | Handle permission prompts and unexpected interactive behavior; some operations may still prompt |
| SQLite from async context | Using `sqlite3` module directly in async handlers | Use `aiosqlite` or run sqlite3 in a thread worker via Textual's `@work(thread=True)` |
| Claude CLI error codes | Parsing only stdout, ignoring stderr and exit codes | Check exit code, capture stderr, implement retry with exponential backoff for transient errors |
| Textual widget updates from workers | Calling `widget.update()` from a thread worker | Use `App.call_from_thread()` or post messages via `self.post_message()` from thread workers |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Re-rendering full TUI on every streaming line | UI flickers, high CPU during agent output | Batch updates: accumulate lines and update widget every 100ms, not per-line | Immediately with fast-streaming agents |
| Loading full session history into memory | Slow startup, high memory after many sessions | Lazy-load from SQLite; only load current session; paginate history | After 10-20 sessions with large outputs |
| Unbounded agent output in TUI RichLog/TextLog | Widget becomes sluggish, scrolling lags | Cap displayed lines (e.g., last 1000); store full output in SQLite for review | After 5+ EXECUTE iterations producing code |
| Spawning new subprocess per small orchestrator decision | Process creation overhead (especially on Windows where fork is expensive) | Reuse a long-running Claude CLI process if possible, or batch small decisions | With rapid orchestrator decision cycles |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Passing user input directly in subprocess command arguments | Command injection via crafted project names or prompts | Use list-form arguments with `asyncio.create_subprocess_exec` (not `shell=True`), validate/sanitize all user inputs |
| Storing Claude API keys in SQLite session database | Key exposure if database is shared or backed up | Never store API keys; rely on Claude CLI's own authentication; store only session data |
| Running `--dangerously-skip-permissions` without understanding scope | Claude CLI can execute arbitrary code, modify filesystem | Sandbox project folders; never point agents at system directories; document the risk clearly |
| Logging full Claude responses including potential secrets | Sensitive data in logs/database | Sanitize logs; never log API keys or credentials that might appear in generated code |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No progress indication during agent execution | User thinks app is frozen, force-quits | Show streaming output, elapsed time, token count, and "Agent working..." animation |
| Blocking keyboard input during agent runs | Cannot cancel, cannot switch panels, trapped | Run agents in workers; keep UI responsive; Ctrl+C cancels current agent |
| Dumping raw markdown/code without syntax highlighting | Wall of unreadable text | Use Rich/Textual's built-in Markdown and Syntax widgets for rendering |
| No way to see previous iterations | User loses context of what changed | Session history panel with diff view between iterations |
| Requiring mouse for panel resizing | Breaks keyboard-first workflow promise | Keyboard shortcuts for panel focus/resize (the project plans this -- enforce it) |
| Silent failures when Claude CLI is not installed or auth expired | Confusing error state | Check Claude CLI availability and auth status on startup; show clear error with fix instructions |

## "Looks Done But Isn't" Checklist

- [ ] **Streaming output:** Often missing proper handling of incomplete UTF-8 sequences at chunk boundaries -- verify with multibyte characters (CJK, emoji in Claude responses)
- [ ] **Agent retry logic:** Often missing exponential backoff and max-retry limits -- verify that 3 consecutive failures do not retry forever
- [ ] **Session persistence:** Often missing crash recovery -- verify that killing the app mid-agent preserves the session state written so far
- [ ] **Panel layout:** Often missing Windows Terminal-specific testing -- verify rendering with both Windows Terminal and legacy conhost
- [ ] **Orchestrator decisions:** Often missing logging of WHY a decision was made -- verify that every routing decision is logged with the input that triggered it
- [ ] **Output contracts:** Often missing validation -- verify that malformed agent output triggers retry, not a crash
- [ ] **Project folder creation:** Often missing path sanitization -- verify that project names with spaces, unicode, or special characters work on Windows

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Subprocess deadlock | LOW | Kill the Claude CLI process, retry the agent call; add stream reading fix |
| Structured output parse failure | LOW | Log raw output, retry with same prompt (non-deterministic = may work next time); if persistent, simplify the output contract |
| TUI event loop blocked | MEDIUM | Requires refactoring blocking calls to workers; identify blocking call via profiling |
| Orchestrator infinite loop | LOW | Kill current cycle, show accumulated output to user, let them decide next step manually |
| Context window exhaustion | MEDIUM | Redesign context passing strategy; implement summarization; requires touching all agent call sites |
| SQLite database locked | LOW | Enable WAL mode; if already locked, retry with timeout; restructure to single-writer pattern |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Subprocess deadlocks | Phase 1 (subprocess infra) | Unit test: stream 1MB+ output without hang |
| Structured output parsing | Phase 1-2 (agent contracts) | Test with intentionally malformed outputs; measure parse success rate over 100 runs |
| Event loop blocking | Phase 1 (TUI foundation) | No operation in message handlers takes >50ms; profile with Textual devtools |
| Orchestrator loops | Phase 2-3 (orchestrator) | Integration test: orchestrator with adversarial agent that always requests changes; verify it stops |
| Context exhaustion | Phase 2 (agent pipeline) | Monitor token counts per call; verify no call exceeds 60% of context window after 3 iterations |
| stream-json handling | Phase 1 (streaming display) | End-to-end test: stream a real Claude response and verify TUI shows progressive output |
| SQLite concurrency | Phase 1 (persistence) | Concurrent read+write test with WAL mode enabled |
| Windows rendering | Phase 1 (TUI foundation) | Manual testing on Windows Terminal and VS Code integrated terminal |
| Agent output sanitization | Phase 1 (display) | Feed terminal escape sequences through display pipeline; verify no corruption |

## Sources

- [Textual Workers Guide](https://textual.textualize.io/guide/workers/) -- official documentation on concurrency patterns
- [Multi-agent workflows often fail (GitHub Blog)](https://github.blog/ai-and-ml/generative-ai/multi-agent-workflows-often-fail-heres-how-to-engineer-ones-that-dont/) -- engineering recommendations for multi-agent systems
- [Python asyncio subprocess documentation](https://docs.python.org/3/library/asyncio-subprocess.html) -- official subprocess streaming patterns
- [Claude CLI stream-json issue #15511](https://github.com/anthropics/claude-code/issues/15511) -- structured output streaming limitation
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference) -- output format options
- [aiosqlite](https://github.com/omnilib/aiosqlite) -- async SQLite bridge for Python
- [json_repair](https://github.com/mangiucugna/json_repair) -- LLM malformed JSON repair library
- [Textual FAQ](https://textual.textualize.io/FAQ/) -- platform-specific rendering notes
- [7 Things learned building a modern TUI Framework](https://www.textualize.io/blog/7-things-ive-learned-building-a-modern-tui-framework/) -- framework author's lessons learned

---
*Pitfalls research for: AI Agent Workflow Console (TUI multi-agent orchestration)*
*Researched: 2026-03-11*
