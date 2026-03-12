# AI Agent Workflow Console

## What This Is

A web-based multi-agent platform that orchestrates AI workflows using Claude CLI. Accessible from any browser at `console.amcsystem.uk`, it lets a developer launch AI tasks from one device and check results hours later from another. The system runs a PROMPT → PLAN → EXECUTE → REVIEW pipeline with an AI-driven orchestrator, supporting both supervised (approve each stage) and fully autonomous execution modes. Deployed on Coolify behind Traefik on an OVH VPS.

## Core Value

The orchestrator must reliably coordinate agents through iterative cycles — taking a rough idea and producing complete, usable code output with zero manual agent management. Tasks persist and stream across devices.

## Current Milestone: v2.0 Web Platform

**Goal:** Transform from local TUI to persistent web platform accessible from any device, with task parallelism, GitHub integration, and hybrid autonomy.

**Target features:**
- FastAPI backend with WebSocket streaming and REST API
- PostgreSQL persistence (tasks, steps, logs) replacing SQLite
- Browser-based dashboard with Alpine.js (no build step)
- Task parallelism with asyncio semaphore (max 2 concurrent Claude CLI)
- Hybrid autonomy: supervised (approve each stage) or autonomous per-task
- GitHub integration: clone repos, commit, push, create PRs
- Docker deployment on Coolify at console.amcsystem.uk

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

### Active

- [ ] Web-based dashboard accessible from any browser
- [ ] Persistent tasks visible across devices
- [ ] Hybrid autonomy (supervised or autonomous per-task)
- [ ] GitHub integration (clone, push, PR)
- [ ] Task parallelism (multiple concurrent tasks)
- [ ] WebSocket streaming with late-join replay
- [ ] PostgreSQL persistence replacing SQLite
- [ ] Docker deployment on Coolify

### Out of Scope

- Multi-user / team features — single-user with basic auth
- Multi-model support (OpenAI, Gemini) — Claude CLI only by design
- Direct API calls — CLI handles auth, tools, MCP, permissions
- Voice input — keyboard-first is the value proposition
- Message queues (Celery/Redis/RabbitMQ) — asyncio semaphore sufficient for single user
- React/Vue/Svelte — Alpine.js sufficient for single-user dashboard
- TUI maintenance — v2.0 replaces TUI with web interface

## Context

v1.0 shipped as TUI with 4,524 LOC Python, 160 tests, 5 phases.
~70% of core modules (agents, runner, parser, context, pipeline) reusable directly.
TUI modules (app, panels, actions, streaming, status_bar) and SQLite layer fully replaced.

VPS: OVH 4-core, 7.6GB RAM, Ubuntu 24.04, Coolify 4.0.
Existing services: PostgreSQL 16, n8n (amcsystem.uk), Evolution API (evo.amcsystem.uk).
Estimated RAM budget: ~2.45GB used / 7.6GB total (5GB margin).

## Constraints

- **Runtime**: Claude CLI via subprocess — Pro Max subscription, no API key
- **Framework**: Python + FastAPI backend, Alpine.js + Pico CSS frontend
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
| FastAPI over Django/Flask | Async-native, WebSocket support, Pydantic models | — Pending |
| PostgreSQL over SQLite | VPS already has it, multi-writer, accessible from n8n | — Pending |
| asyncio.Event for approval gates | Simplest pause/resume pattern for supervised mode | — Pending |
| Alpine.js over React/Vue | No build step, sufficient for single-user dashboard | — Pending |
| No message broker | Single user, 2-3 concurrent tasks, asyncio semaphore enough | — Pending |

---
*Last updated: 2026-03-12 after v2.0 milestone start*
