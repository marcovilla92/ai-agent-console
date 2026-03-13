---
phase: 11-docker-deployment
plan: 01
subsystem: infra
tags: [docker, dockerfile, coolify, python, nodejs, claude-cli, playwright]

requires:
  - phase: 10-dashboard-frontend
    provides: "Complete FastAPI application with templates and static assets"
provides:
  - "Docker image with Python 3.12, Node.js 22, Claude CLI 2.1.74"
  - "Dockerfile for Coolify deployment with Traefik proxy"
  - ".dockerignore excluding dev files from build context"
  - "Live deployment at console.amcsystem.uk with full E2E functionality"
affects: [deployment, coolify, production]

tech-stack:
  added: [docker, nodesource-22]
  patterns: [layer-cached-pip-install, slim-base-image, non-root-container]

key-files:
  created: [Dockerfile, .dockerignore]
  modified: [requirements.txt]

key-decisions:
  - "python:3.12-slim over alpine -- Claude CLI Node.js native modules need glibc"
  - "Pin Claude CLI to v2.1.74 for reproducible builds"
  - "Single requirements.txt (no prod/dev split) -- acceptable for single-user project"
  - "No HEALTHCHECK directive -- Coolify handles health checks via /health endpoint"
  - "Non-root appuser -- Claude CLI refuses --dangerously-skip-permissions as root"
  - "Reused existing n8n PostgreSQL with dedicated agent_console database"
  - "Coolify Directory Mount via DB insert (Livewire form click unreliable via Playwright)"
  - "uvicorn[standard] for WebSocket support"

patterns-established:
  - "Docker layer caching: COPY requirements.txt before src/ for pip cache reuse"
  - "Single RUN for apt-get update + install + cleanup to minimize layer size"
  - "Playwright headless automation for Coolify dashboard configuration"
  - "Coolify API (Bearer token) for app config updates"

requirements-completed: [INFR-03]

duration: 45min
completed: 2026-03-13
---

# Phase 11 Plan 01: Docker Deployment Summary

**Dockerfile with Python 3.12-slim, Node.js 22, and Claude CLI 2.1.74 deployed on Coolify at console.amcsystem.uk -- full E2E verified**

## Performance

- **Duration:** ~45 min (including iterative fixes)
- **Started:** 2026-03-13T08:46:14Z
- **Completed:** 2026-03-13T14:40:00Z
- **Tasks:** 2 of 2 (both completed)
- **Files modified:** 3

## Accomplishments
- Docker image builds successfully with all runtime dependencies
- Claude CLI v2.1.74 confirmed executable inside container as non-root user
- Image size 621MB (well under 800MB target)
- .dockerignore excludes .git, .planning, tests, docs, __pycache__, .env
- Application deployed and running on Coolify at console.amcsystem.uk
- Full E2E verified: task created from UI, Claude executed it, output displayed
- Health endpoint returns `{"status":"ok","database":"connected"}`
- WebSocket support enabled via uvicorn[standard]

## Task Commits

1. **Task 1: Create Dockerfile and .dockerignore** - `9127af2` (feat)
2. **Fix: Add jinja2 dependency** - `05f2de1` (fix)
3. **Fix: Add websockets + non-root user** - `c63f32a` (fix)
4. **Task 2: Deploy on Coolify** - Completed via Playwright + API automation

## Coolify Configuration Applied
- **Build pack:** Dockerfile (changed from Nixpacks)
- **Branch:** master (changed from main)
- **Port:** 8000
- **Domain:** console.amcsystem.uk (DNS A record on Cloudflare)
- **Env vars:** APP_DATABASE_URL, APP_AUTH_USERNAME, APP_AUTH_PASSWORD, APP_PROJECT_PATH, APP_PORT
- **Volume mounts:** /home/ubuntu/.claude -> /home/appuser/.claude, /home/ubuntu/projects -> /workspace
- **Database:** agent_console on existing PostgreSQL 16 (shared with n8n)

## Files Created/Modified
- `Dockerfile` - Python 3.12-slim, Node.js 22, Claude CLI, non-root appuser
- `.dockerignore` - Excludes dev files
- `requirements.txt` - Added jinja2>=3.1, changed uvicorn to uvicorn[standard]

## Deviations from Plan

1. **Non-root user added** - Claude CLI refuses `--dangerously-skip-permissions` as root. Added `appuser` to Dockerfile.
2. **Missing dependencies** - jinja2 and websockets were missing from requirements.txt. Fixed during deployment.
3. **Reused existing PostgreSQL** - Created `agent_console` database on existing n8n PostgreSQL instead of deploying a dedicated instance. Same Docker network, simpler setup.
4. **Automated Coolify config** - Used Playwright + Coolify API instead of manual UI steps. Coolify API for app settings, direct DB insert for directory mounts.
5. **Volume mount path** - Changed from /root/.claude to /home/appuser/.claude due to non-root user.

## Issues Encountered

1. **jinja2 not installed** - Container crashed on startup. Fixed by adding to requirements.txt.
2. **WebSocket unsupported** - uvicorn needs `uvicorn[standard]` for WebSocket. Fixed.
3. **Claude CLI root restriction** - `--dangerously-skip-permissions` blocked as root. Fixed with non-root user.
4. **Coolify customDockerRunOptions** - `-v` flags in this field are silently ignored by Coolify. Used Directory Mount via DB insert instead.
5. **DNS propagation** - Added /etc/hosts entry on server for local testing while Cloudflare DNS propagated.

## E2E Test Results

| Test | Result |
|------|--------|
| `/health` | 200 - `{"status":"ok","database":"connected"}` |
| Dashboard (`/`) | 200 - AI Agent Console HTML |
| Task creation | Task created, Claude executed, status: completed |
| Claude CLI in container | Responds correctly as appuser |
| Volume mounts | .claude credentials and /workspace accessible |

---
*Phase: 11-docker-deployment*
*Completed: 2026-03-13*
