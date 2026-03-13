---
phase: 11-docker-deployment
plan: 01
subsystem: infra
tags: [docker, dockerfile, coolify, python, nodejs, claude-cli]

requires:
  - phase: 10-dashboard-frontend
    provides: "Complete FastAPI application with templates and static assets"
provides:
  - "Docker image with Python 3.12, Node.js 22, Claude CLI 2.1.74"
  - "Dockerfile for Coolify deployment with Traefik proxy"
  - ".dockerignore excluding dev files from build context"
affects: [deployment, coolify, production]

tech-stack:
  added: [docker, nodesource-22]
  patterns: [layer-cached-pip-install, slim-base-image]

key-files:
  created: [Dockerfile, .dockerignore]
  modified: []

key-decisions:
  - "python:3.12-slim over alpine -- Claude CLI Node.js native modules need glibc"
  - "Pin Claude CLI to v2.1.74 for reproducible builds"
  - "Single requirements.txt (no prod/dev split) -- acceptable for single-user project"
  - "No HEALTHCHECK directive -- Coolify handles health checks via /health endpoint"

patterns-established:
  - "Docker layer caching: COPY requirements.txt before src/ for pip cache reuse"
  - "Single RUN for apt-get update + install + cleanup to minimize layer size"

requirements-completed: [INFR-03]

duration: 2min
completed: 2026-03-13
---

# Phase 11 Plan 01: Docker Deployment Summary

**Dockerfile with Python 3.12-slim, Node.js 22, and Claude CLI 2.1.74 for Coolify deployment at 621MB image size**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-13T08:46:14Z
- **Completed:** 2026-03-13T08:49:00Z
- **Tasks:** 1 of 2 (Task 2 is checkpoint:human-verify for Coolify deployment)
- **Files modified:** 2

## Accomplishments
- Docker image builds successfully with all runtime dependencies
- Claude CLI v2.1.74 confirmed executable inside container
- Image size 621MB (well under 800MB target)
- .dockerignore excludes .git, .planning, tests, docs, __pycache__, .env

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Dockerfile and .dockerignore** - `9127af2` (feat)
2. **Task 2: Deploy on Coolify and verify live access** - PENDING (checkpoint:human-verify)

## Files Created/Modified
- `Dockerfile` - Multi-stage build with Python 3.12-slim, Node.js 22, Claude CLI, pip deps, and uvicorn CMD
- `.dockerignore` - Excludes dev files (.git, .planning, tests, docs, __pycache__, .env, .claude)

## Decisions Made
- Used python:3.12-slim (not alpine) because Claude CLI Node.js native modules need glibc
- Pinned Claude CLI to v2.1.74 matching host version for reproducibility
- Kept single requirements.txt rather than splitting prod/dev -- acceptable for single-user project
- No HEALTHCHECK in Dockerfile -- Coolify manages health checks via /health endpoint
- --no-install-recommends and apt cache cleanup in same RUN layer to minimize image size

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

Task 2 requires manual Coolify configuration. The user must:
1. Deploy PostgreSQL 16 via Coolify
2. Create application from GitHub repo with Dockerfile build pack
3. Configure env vars (APP_DATABASE_URL, APP_AUTH_USERNAME, APP_AUTH_PASSWORD, APP_PROJECT_PATH)
4. Set domain to console.amcsystem.uk
5. Add volume mounts (~/.claude:/root/.claude:ro, ~/projects/workspace:/workspace)
6. Ensure app and PostgreSQL share the same Docker network
7. Deploy via Coolify UI or push to trigger auto-deploy

## Next Phase Readiness
- Docker image ready for deployment
- Coolify configuration documented in plan
- Awaiting user action for live deployment and verification

---
*Phase: 11-docker-deployment*
*Completed: 2026-03-13*
