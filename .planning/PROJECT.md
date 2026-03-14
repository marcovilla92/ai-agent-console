# AI Agent Workflow Console

## What This Is

A web-based multi-agent platform that orchestrates AI workflows using Claude CLI. Accessible from any browser at `console.amcsystem.uk`, it lets a developer launch AI tasks from one device and check results hours later from another. The system runs a PROMPT → PLAN → EXECUTE → REVIEW pipeline with an AI-driven orchestrator, supporting both supervised (approve each stage) and fully autonomous execution modes. Deployed on Coolify behind Traefik on an OVH VPS.

## Core Value

The orchestrator must reliably coordinate agents through iterative cycles — taking a rough idea and producing complete, usable code output with zero manual agent management. Tasks persist and stream across devices.

## Current Milestone: v2.2 UI Redesign

**Goal:** Complete visual overhaul — clean light theme, fixed sidebar navigation, KPI dashboard cards, expandable task lists, and modern design system with Tailwind CSS.

**Target features:**
- Fixed sidebar navigation (Projects, Templates, Tasks)
- Clean light theme with modern typography and spacing
- Fully responsive design (desktop, tablet, phone) — sidebar collapses on mobile
- Project dashboard with KPI cards (status at a glance) + expandable task list
- Template browser with card grid layout
- Streamlined task creation and improved streaming output view
- Tailwind CSS design system replacing Pico CSS
- Loading states and smooth transitions

## Requirements

### Validated

- ✓ 3-agent pipeline (Plan/Execute/Review) with config-driven registry — v1.0
- ✓ AI-driven orchestrator decides next agent via Claude CLI with JSON schema — v1.0
- ✓ Iterative review cycles with user confirmation and cycle detection (3 iteration limit) — v1.0
- ✓ Structured handoffs visible between agents — v1.0
- ✓ Extensible agent architecture (pluggable agents via config) — v1.0
- ✓ Workspace context shared across agents — v1.0
- ✓ Real-time streaming output from Claude CLI — v1.0
- ✓ Retry logic (3 attempts, exponential backoff) on Claude CLI errors — v1.0
- ✓ Git auto-commit after successful execution cycles — v1.0
- ✓ Token usage and cost tracking — v1.0
- ✓ Web-based dashboard accessible from any browser — v2.0
- ✓ Persistent tasks visible across devices — v2.0
- ✓ Hybrid autonomy (supervised or autonomous per-task) — v2.0
- ✓ Task parallelism (multiple concurrent tasks) — v2.0
- ✓ WebSocket streaming with late-join replay — v2.0
- ✓ PostgreSQL persistence replacing SQLite — v2.0
- ✓ Docker deployment on Coolify — v2.0

### Active

- [ ] Complete UI redesign with clean light theme and Tailwind CSS
- [ ] Fixed sidebar navigation with responsive collapse
- [ ] KPI dashboard cards per project
- [ ] Expandable task list with status badges and output preview
- [ ] Template browser with card grid layout
- [ ] Fully responsive design (desktop, tablet, phone)

### Out of Scope

- Multi-user / team features — single-user with basic auth
- Multi-model support (OpenAI, Gemini) — Claude CLI only by design
- Direct API calls — CLI handles auth, tools, MCP, permissions
- Voice input — keyboard-first is the value proposition
- Message queues (Celery/Redis/RabbitMQ) — asyncio semaphore sufficient for single user
- React/Vue/Svelte — Alpine.js + Tailwind CSS sufficient for single-user dashboard
- TUI maintenance — v2.0 replaces TUI with web interface
- GitHub integration (clone, push, PR) — deferred from v2.0, not needed for project router
- n8n webhook implementation — only hook points/placeholders in v2.1

## Context

v1.0 shipped as TUI with 4,524 LOC Python, 160 tests, 5 phases.
v2.0 shipped as web platform: FastAPI + asyncpg + Alpine.js, 6 phases (06-11), deployed on Coolify.
App live at console.amcsystem.uk with WebSocket streaming, approval gates, task parallelism.

VPS: OVH 4-core, 7.6GB RAM, Ubuntu 24.04, Coolify 4.0.
Existing services: PostgreSQL 16, n8n (amcsystem.uk), Evolution API (evo.amcsystem.uk).
Design spec: docs/project-router-spec.md (808 lines, full API/DB/UX spec for v2.1).

## Constraints

- **Runtime**: Claude CLI via subprocess — Pro Max subscription, no API key
- **Framework**: Python + FastAPI backend, Alpine.js + Tailwind CSS frontend
- **Platform**: OVH VPS (Ubuntu 24.04), Docker via Coolify, Traefik proxy
- **Storage**: PostgreSQL 16 (existing instance), workspace volumes for cloned repos
- **Concurrency**: Max 2 Claude CLI processes (asyncio.Semaphore) — RAM constraint
- **Agent communication**: Structured output contracts via system prompts
- **Orchestrator**: AI-driven via Claude CLI (not rule-based)
- **Auth**: HTTP Basic Auth (single user)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Textual for TUI (v1.0) | Modern Python TUI framework | ✓ Good — validated agent pipeline patterns |
| AI-driven orchestrator | More flexible than rule-based | ✓ Good — JSON schema enforcement works |
| stream_claude yields dict for result events | isinstance check distinguishes text from metadata | ✓ Good — reusable in web version |
| FastAPI over Django/Flask | Async-native, WebSocket support, Pydantic models | ✓ Good — v2.0 shipped successfully |
| PostgreSQL over SQLite | VPS already has it, multi-writer, accessible from n8n | ✓ Good — asyncpg works well |
| asyncio.Event for approval gates | Simplest pause/resume pattern for supervised mode | ✓ Good — lightweight, no external deps |
| Alpine.js over React/Vue | No build step, sufficient for single-user dashboard | ✓ Good — simple and effective |
| No message broker | Single user, 2-3 concurrent tasks, asyncio semaphore enough | ✓ Good — sufficient for workload |
| Full SPA replacing Jinja2 templates | No delimiter conflicts, clean API separation | — Pending |
| templates/ for project scaffolding | Jinja2 HTML templates removed, directory repurposed | — Pending |
| Manual project selection (no auto-detect) | Explicit user choice, predictable behavior | — Pending |

---
*Last updated: 2026-03-14 after v2.2 milestone start*
