# Feature Research

**Domain:** Terminal-based multi-agent AI coding console (TUI orchestrator)
**Researched:** 2026-03-11
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Real-time streaming output | Every competitor streams (Claude Code, aider, OpenCode, Toad). Waiting for full response with no feedback is unacceptable | MEDIUM | Subprocess stdout streaming into Textual widgets. Claude CLI supports streaming natively |
| Session persistence | OpenCode, Conduit, Ralph TUI all persist sessions via SQLite. Users expect to close terminal and resume later | MEDIUM | SQLite is the standard choice (OpenCode, project spec already chose this) |
| Keyboard-driven workflow | Terminal users demand keyboard-first UX. Toad, Conduit, OpenCode all have extensive keybindings | LOW | Textual has built-in keybinding support. Map Ctrl+shortcuts to agent actions |
| Multi-file context awareness | Aider, Claude Code, OpenCode all track multiple files in context. Agent must know what files exist and what they contain | MEDIUM | Workspace scanning + file list passed in system prompts. Context window management is the hard part |
| Status/progress indicators | Every tool shows current state: what agent is running, token usage, cost. Conduit shows real-time token tracking in status bar | LOW | Textual status bar widget. Show agent name, step count, token usage |
| Error handling with retry | Claude CLI can fail (rate limits, network). Users expect graceful recovery, not crashes. Ralph TUI has exponential backoff and agent failover | LOW | Already spec'd: 3-attempt retry. Add exponential backoff |
| Dark theme terminal UI | Every modern TUI tool uses dark theme by default (OpenCode, Toad, Conduit). Light theme in terminal is jarring | LOW | Textual supports themes natively. Ship dark-only initially |
| Git integration (basic) | Aider auto-commits changes. Claude Code manages git. Users expect at minimum: show git status, auto-commit agent outputs | MEDIUM | Auto-commit after successful EXECUTE cycle. Show diff in REVIEW panel |
| Structured agent output | Claude Code uses structured outputs. OpenCode separates Build/Plan agents with contracts. Predictable output is essential for orchestration | MEDIUM | Already spec'd: GOAL/TASKS/ARCHITECTURE/FILES/HANDOFF contracts via system prompts |
| Project/workspace isolation | Every tool scopes to a project directory. OpenCode auto-detects projects. Goose creates isolated workspaces | LOW | Already spec'd: project creation flow with dedicated folders |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| AI-driven orchestrator (not rule-based) | Most tools use simple sequential pipelines or manual agent switching (Conduit). An AI deciding "what next" based on output quality is genuinely novel for a personal TUI tool. Ralph TUI uses algorithmic task selection; this project uses LLM-driven orchestration | HIGH | Core differentiator. The orchestrator itself calls Claude CLI to analyze outputs and decide next action. No other personal TUI tool does autonomous multi-step orchestration this way |
| 4-panel collapsible layout (PROMPT/PLAN/EXECUTE/REVIEW) | Most tools are single-pane chat (aider, Claude Code) or tabbed (Conduit). A dedicated panel per workflow stage gives visibility into the full pipeline simultaneously. Similar to Ralph TUI's "mission control" concept but with richer per-stage views | MEDIUM | Textual supports collapsible panels, splitters, docking. The 4-panel metaphor maps to the agent pipeline naturally |
| Iterative review cycles with AI decision loop | Aider has a simple edit-test loop. Claude Code runs once per prompt. This project's REVIEW agent can trigger re-PLAN or re-EXECUTE autonomously, creating quality-driven iteration without user babysitting | HIGH | The REVIEW agent output includes a DECISION field (APPROVE/REVISE/REJECT). Orchestrator acts on it. This is the "keep going until it's right" UX that most tools lack |
| Visible agent handoff contracts | No competitor shows the structured handoff between agents visibly in the UI. Seeing PLAN output flow into EXECUTE input builds trust and debuggability | LOW | Display HANDOFF sections prominently between panels. Users see exactly what context each agent received |
| Pluggable agent architecture | Goose has MCP extensions. Aider has modes. But few TUI tools let you define new agents with just a system prompt and output contract. This enables future DEBUG/TEST/DEPLOY agents without code changes | MEDIUM | Agent = (name, system_prompt, output_contract, panel_assignment). Registry pattern. New agents are config, not code |
| Cost/token tracking per agent per cycle | Conduit tracks tokens. But showing cost breakdown per agent per iteration cycle (PLAN cost vs EXECUTE cost vs REVIEW cost) helps users understand where money goes | LOW | Parse Claude CLI output for token counts. Aggregate per agent per cycle. Display in status bar and session history |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Direct API calls instead of CLI subprocess | "CLI is a hack, API is proper" | CLI handles auth, model selection, tool use, MCP servers, permissions. Reimplementing all that is massive scope. CLI is how Anthropic ships Claude Code itself | Use Claude CLI via subprocess. Benefit from all CLI improvements for free. Parse structured output from stdout |
| Web UI / browser dashboard | "Terminal is limiting, web is more visual" | Doubles the codebase. Splits focus. TUI-first is the identity of this tool. Toad proves Textual can be visually rich | Invest in Textual's rich rendering: markdown, syntax highlighting, collapsible sections. TUI can look great |
| Multi-model support (OpenAI, Gemini, etc.) | "Don't lock me to one provider" | Each model has different output formats, capabilities, token limits. Orchestrator prompts are tuned for Claude. Multi-model support means testing matrix explodes | Ship Claude-only. Claude CLI already supports model selection within Anthropic's lineup. If needed later, add via pluggable agent architecture where different agents can use different CLI backends |
| Real-time collaboration / multi-user | "Teams need to share sessions" | Massively increases complexity: auth, sync, conflict resolution. This is a personal productivity tool | Stay single-user. Export session summaries as markdown for sharing |
| GUI file tree / visual file browser | "Show me the project structure visually" | Reinventing what the terminal already does well. Adds widget complexity for marginal value | Show file list in context panel. User can `ls` in their own terminal. Focus on what files the agent is working on, not browsing |
| Auto-run generated code | "Just execute what the agent writes" | Dangerous without review. Even Claude Code requires `--dangerously-skip-permissions` for a reason | Show generated code in EXECUTE panel. User confirms before any execution. REVIEW agent checks code quality first |
| Plugin marketplace / ecosystem | "Let the community build extensions" | Premature. Need core stability first. Plugin APIs are expensive to maintain and get wrong | Pluggable agent architecture is sufficient. JSON config for new agents. No need for a package manager |
| Voice input | "Aider supports voice, we should too" | Adds audio dependency, speech-to-text complexity. Niche usage in terminal context | Defer entirely. Keyboard-first is the value prop. If needed, external speech-to-text can pipe into the prompt field |

## Feature Dependencies

```
[Streaming Output]
    └──requires──> [Claude CLI Subprocess Management]
                       └──requires──> [Process Lifecycle (spawn, kill, retry)]

[AI-Driven Orchestrator]
    └──requires──> [Structured Agent Output Contracts]
                       └──requires──> [System Prompt Templates]
    └──requires──> [Agent Registry]
    └──requires──> [Session State Management]

[4-Panel Layout]
    └──requires──> [Textual Widget Tree]
    └──requires──> [Streaming Output] (to populate panels in real-time)

[Iterative Review Cycles]
    └──requires──> [AI-Driven Orchestrator]
    └──requires──> [REVIEW Agent with DECISION output]
    └──requires──> [Session Persistence] (to track iteration history)

[Session Persistence]
    └──requires──> [SQLite Schema]
    └──requires──> [Agent Output Serialization]

[Git Integration]
    └──requires──> [Project/Workspace Isolation]
    └──enhances──> [REVIEW Agent] (show diffs for review)

[Pluggable Agent Architecture]
    └──requires──> [Agent Registry]
    └──requires──> [Structured Agent Output Contracts]
    └──enhances──> [AI-Driven Orchestrator]

[Cost/Token Tracking]
    └──requires──> [Claude CLI Output Parsing]
    └──enhances──> [Status Bar]
    └──enhances──> [Session Persistence]
```

### Dependency Notes

- **AI-Driven Orchestrator requires Structured Contracts:** The orchestrator can only decide "what next" if agent outputs are predictable and parseable. Contracts must be built and tested before orchestration logic.
- **Iterative Review requires Orchestrator:** The review loop is the orchestrator's primary workflow. Without the orchestrator, review is manual.
- **4-Panel Layout requires Streaming:** Panels without live-updating content are just static text boxes. Streaming is what makes the layout feel alive.
- **Pluggable Agents enhance Orchestrator:** New agents only matter if the orchestrator knows how to invoke them and interpret their output.
- **Git Integration enhances Review:** Showing file diffs in the REVIEW panel is far more useful than raw code output.

## MVP Definition

### Launch With (v1)

Minimum viable product -- what's needed to validate the concept.

- [ ] Claude CLI subprocess with streaming output -- foundation for everything
- [ ] 4-panel TUI layout (Prompt, Plan, Execute, Review) -- the visual identity
- [ ] PLAN agent with structured output contract -- first agent in the pipeline
- [ ] EXECUTE agent with structured output contract -- produces the actual code
- [ ] REVIEW agent with DECISION output (APPROVE/REVISE/REJECT) -- closes the loop
- [ ] AI-driven orchestrator (decides next agent based on output) -- the core differentiator
- [ ] Session persistence via SQLite -- resume work across sessions
- [ ] Keyboard shortcuts for all actions -- terminal-first UX
- [ ] Project folder creation and workspace isolation -- one project = one folder
- [ ] Basic status bar (current agent, state, step count) -- know what's happening

### Add After Validation (v1.x)

Features to add once core is working.

- [ ] Git auto-commit after successful cycles -- when orchestrator loop is proven stable
- [ ] Token/cost tracking per agent -- when users start caring about spend
- [ ] Iterative review cycles (auto-retry on REVISE) -- when single-pass quality is validated
- [ ] Visible handoff contracts between panels -- when users want to debug agent decisions
- [ ] Resizable/collapsible panels -- when layout preferences emerge from usage
- [ ] Session history browser (past sessions list) -- when session count grows

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] Pluggable agent architecture (add agents via config) -- when PLAN/EXECUTE/REVIEW prove the pattern
- [ ] Parallel agent execution -- when sequential is proven too slow for specific workflows
- [ ] DEBUG/TEST/DEPLOY agents -- when the core three agents are rock solid
- [ ] Export session as markdown report -- when sharing becomes a need
- [ ] Customizable themes -- when dark-only gets complaints
- [ ] MCP server integration -- when external tool access becomes necessary

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Claude CLI streaming subprocess | HIGH | MEDIUM | P1 |
| 4-panel TUI layout | HIGH | MEDIUM | P1 |
| PLAN agent + contract | HIGH | LOW | P1 |
| EXECUTE agent + contract | HIGH | LOW | P1 |
| REVIEW agent + DECISION | HIGH | LOW | P1 |
| AI-driven orchestrator | HIGH | HIGH | P1 |
| Session persistence (SQLite) | HIGH | MEDIUM | P1 |
| Keyboard shortcuts | HIGH | LOW | P1 |
| Project workspace isolation | MEDIUM | LOW | P1 |
| Status bar | MEDIUM | LOW | P1 |
| Error handling + retry | HIGH | LOW | P1 |
| Git auto-commit | MEDIUM | MEDIUM | P2 |
| Token/cost tracking | MEDIUM | LOW | P2 |
| Iterative auto-retry | HIGH | MEDIUM | P2 |
| Visible handoff contracts | MEDIUM | LOW | P2 |
| Resizable panels | LOW | LOW | P2 |
| Session history browser | MEDIUM | MEDIUM | P2 |
| Pluggable agent architecture | MEDIUM | HIGH | P3 |
| Parallel agent execution | LOW | HIGH | P3 |
| Additional agents (DEBUG, TEST) | MEDIUM | MEDIUM | P3 |
| Export as markdown | LOW | LOW | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Aider | Claude Code | OpenCode | Toad | Conduit | Ralph TUI | Our Approach |
|---------|-------|-------------|----------|------|---------|-----------|--------------|
| TUI (not just CLI) | No (CLI chat) | No (CLI chat) | Yes (themed TUI) | Yes (Textual) | Yes (tabbed TUI) | Yes (dashboard) | Yes (4-panel Textual TUI) |
| Multi-agent orchestration | No (single agent, architect+editor) | Yes (Agent Teams, experimental) | No (dual agent, manual) | No (frontend only) | No (manual tab switching) | Yes (task loop, algorithmic) | Yes (AI-driven, autonomous) |
| Structured pipeline (Plan/Execute/Review) | No | No | Partial (Build/Plan separation) | No | No | Partial (task-based) | Yes (explicit 3-stage pipeline) |
| AI decides next step | No (user-driven) | Partial (within single agent) | No | No | No | Algorithmic (priority-based) | Yes (LLM-driven orchestrator) |
| Streaming output | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Session persistence | Partial (chat history) | Yes | Yes (SQLite) | No | Yes | Yes | Yes (SQLite) |
| Git integration | Deep (auto-commit) | Deep (native) | Basic | No | Yes (worktrees) | No | Basic (auto-commit cycles) |
| Multi-model support | Yes (any model) | No (Claude only) | Yes (multiple) | Yes (via backends) | Yes (Claude + Codex) | Yes (multiple agents) | No (Claude only, by design) |
| Token/cost tracking | Partial | No | Yes | No | Yes (real-time) | Partial | Yes (per-agent breakdown) |
| Iterative quality loop | Partial (lint+test) | No (single pass) | No | No | No | Yes (task retry) | Yes (REVIEW-driven iteration) |
| Pluggable extensions | No | Yes (MCP) | No | Yes (ACP protocol) | No | Yes (agent configs) | Future (pluggable agents) |

## Sources

- [Aider - AI Pair Programming](https://aider.chat/) - Official site, chat modes docs
- [Aider Chat Modes](https://aider.chat/docs/usage/modes.html) - Architect mode details
- [Claude Code Agent Teams](https://code.claude.com/docs/en/agent-teams) - Official multi-agent docs
- [OpenCode TUI](https://opencode.ai/docs/tui/) - TUI feature documentation
- [OpenCode GitHub](https://github.com/opencode-ai/opencode) - 95K+ stars, open-source reference
- [Toad by Will McGugan](https://willmcgugan.github.io/announcing-toad/) - Textual-based agentic TUI
- [Toad Released](https://willmcgugan.github.io/toad-released/) - Shell integration, notebook UX
- [Conduit - Multi-Agent TUI](https://getconduit.sh/) - Tabbed multi-agent interface
- [Ralph TUI](https://ralph-tui.com/docs/getting-started/introduction) - Agent loop orchestrator
- [Goose GitHub](https://github.com/block/goose) - MCP-first agent, recipes
- [Warp Oz Platform](https://www.warp.dev/blog/oz-orchestration-platform-cloud-agents) - Cloud agent orchestration
- [Cursor CLI Agent Modes](https://forum.cursor.com/t/cursor-cli-jan-16-2026-cli-agent-modes-and-cloud-handoff/149171) - Plan mode, cloud handoff
- [DiffBack](https://github.com/A386official/diffback) - Agent rollback tooling
- [Top 5 CLI Coding Agents 2026](https://pinggy.io/blog/top_cli_based_ai_coding_agents/) - Market overview
- [AgentPipe](https://github.com/kevinelliott/agentpipe) - Multi-agent conversation orchestrator
- [Agentic CLI Tools Compared](https://aimultiple.com/agentic-cli) - Claude Code vs Cline vs Aider

---
*Feature research for: Terminal-based multi-agent AI coding console*
*Researched: 2026-03-11*
