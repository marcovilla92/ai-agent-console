# Phase 11: Docker Deployment - Research

**Researched:** 2026-03-13
**Domain:** Docker containerization, Coolify PaaS, Traefik reverse proxy
**Confidence:** HIGH

## Summary

Phase 11 containerizes the FastAPI application for deployment on the existing Coolify PaaS infrastructure running on an OVH VPS. The server already runs Coolify 4.0.0-beta.467 with Traefik v3.6 as the reverse proxy, PostgreSQL 16, n8n, and Evolution API. The application needs a Dockerfile, proper volume mounts for Claude CLI authentication, and Traefik labels for HTTPS routing to `console.amcsystem.uk`.

The critical complexity is embedding Claude CLI (an npm global package: `@anthropic-ai/claude-code`) inside the container and mounting the host's `~/.claude/` directory so the CLI can authenticate. The application spawns Claude CLI as subprocess calls (`asyncio.create_subprocess_exec`), so the binary must be on PATH inside the container. WebSocket connections require specific Traefik timeout configuration and gzip must be disabled on the WebSocket route to prevent buffering issues.

**Primary recommendation:** Use a Python 3.12-slim base image with Node.js 22 installed for Claude CLI. Deploy via Coolify's GitHub integration with Nixpacks disabled in favor of a custom Dockerfile. Mount `~/.claude/` as a volume for CLI auth persistence.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFR-03 | Application deploys as Docker container on Coolify with Traefik proxy | Dockerfile pattern, Coolify GitHub auto-deploy, Traefik label configuration, WebSocket timeout settings, Claude CLI volume mount strategy |
</phase_requirements>

## Standard Stack

### Core
| Component | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| Python | 3.12-slim | Base runtime | Matches host Python 3.12.3, slim reduces image size |
| Node.js | 22.x | Claude CLI runtime | Claude CLI is an npm package, matches host v22.22.1 |
| @anthropic-ai/claude-code | latest | AI agent subprocess | Application spawns Claude CLI via `shutil.which("claude")` |
| Coolify | 4.0.0-beta.467 | PaaS deployment | Already running on the VPS, manages Docker lifecycle |
| Traefik | v3.6 | Reverse proxy + TLS | Already running as `coolify-proxy`, handles Let's Encrypt |

### Supporting
| Component | Purpose | When to Use |
|-----------|---------|-------------|
| .dockerignore | Exclude dev files from build context | Always -- reduces build time and image size |
| docker-compose.yml | Local development parity | Optional -- Coolify handles orchestration in production |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python slim + Node.js install | Nixpacks auto-build | Nixpacks may not detect Claude CLI need, custom Dockerfile gives full control |
| Volume mount for ~/.claude | Bake credentials into image | NEVER bake credentials -- volume mount is the only safe approach |
| Single-stage build | Multi-stage build | Unnecessary -- no compiled assets, runtime needs both Python and Node.js |

## Architecture Patterns

### Recommended Dockerfile Structure
```dockerfile
FROM python:3.12-slim

# Install Node.js 22 for Claude CLI
RUN apt-get update && apt-get install -y curl git && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Claude CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Install Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ ./src/
COPY pyproject.toml .

# Expose port
EXPOSE 8000

# Run the server
CMD ["python", "-m", "uvicorn", "src.server.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

### Coolify Deployment Pattern (from existing n8n service inspection)
Coolify manages containers with these conventions:
- Each service gets its own Docker network (`<random-id>`)
- Services connect to `coolify` network for Traefik routing
- Traefik labels are applied automatically by Coolify UI configuration
- Let's Encrypt certificates via `certresolver: letsencrypt`
- HTTP-to-HTTPS redirect via `redirect-to-https` middleware

### Traefik Labels Pattern (observed from n8n container)
```
traefik.enable: true
traefik.http.routers.http-0-<id>.entryPoints: http
traefik.http.routers.http-0-<id>.middlewares: redirect-to-https
traefik.http.routers.http-0-<id>.rule: Host(`console.amcsystem.uk`)
traefik.http.routers.https-0-<id>.entryPoints: https
traefik.http.routers.https-0-<id>.rule: Host(`console.amcsystem.uk`)
traefik.http.routers.https-0-<id>.tls: true
traefik.http.routers.https-0-<id>.tls.certresolver: letsencrypt
```

Note: Coolify generates these labels automatically when you configure a domain in the UI. The Dockerfile does NOT need to contain Traefik labels.

### WebSocket Traefik Configuration
WebSocket requires special handling:
- Traefik v3.6 supports WebSocket natively on HTTP routers (no special middleware needed)
- Gzip compression middleware MUST be disabled for WebSocket routes (buffering breaks streaming)
- Timeouts must be extended for long-running tasks

### Environment Variables Pattern
The application uses `APP_` prefix for all settings (from `pydantic_settings`):
```
APP_DATABASE_URL=postgresql://user:pass@host:5432/agent_console
APP_AUTH_USERNAME=admin
APP_AUTH_PASSWORD=<secure-password>
APP_PROJECT_PATH=/workspace
APP_HOST=0.0.0.0
APP_PORT=8000
```

### Volume Mounts Required
```
# Claude CLI auth (read-only is sufficient for auth tokens)
~/.claude:/root/.claude:ro

# Project workspace for agent file operations
~/projects/workspace:/workspace

# Optional: SSH keys for git operations
~/.ssh:/root/.ssh:ro
```

### Anti-Patterns to Avoid
- **Baking secrets into Docker image:** Never COPY .env or credentials. Use environment variables via Coolify UI.
- **Using alpine base:** Claude CLI depends on Node.js native modules that may fail on musl libc. Use debian-based images.
- **Running as root without purpose:** The application spawns subprocesses (Claude CLI), and volume mounts for ~/.claude are owned by root in the container. Running as root is acceptable here since it is a single-user system behind auth.
- **Using `latest` tag for base image:** Pin to `python:3.12-slim` for reproducibility.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TLS termination | Custom cert management | Traefik + Let's Encrypt via Coolify | Automatic cert renewal, zero config |
| HTTP-to-HTTPS redirect | Uvicorn redirect middleware | Traefik redirect-to-https middleware | Handled at proxy layer, no app code needed |
| Container orchestration | Custom deploy scripts | Coolify auto-deploy from GitHub | Watches repo, builds, deploys automatically |
| Health checks | Custom monitoring | Existing `/health` endpoint + Coolify health check | App already has health check endpoint |
| Process management | supervisord / systemd | Single CMD with uvicorn | Single process per container is Docker best practice |

## Common Pitfalls

### Pitfall 1: Claude CLI Auth Fails Inside Container
**What goes wrong:** Claude CLI cannot authenticate because `~/.claude/` directory is missing or unreadable.
**Why it happens:** The Claude CLI stores auth tokens in `~/.claude/` on the host. Without volume mounting this directory, the CLI inside the container has no credentials.
**How to avoid:** Mount host `~/.claude/` to `/root/.claude/` in the container. The container runs as root by default in a Python slim image.
**Warning signs:** `claude` commands fail with auth errors in container logs.

### Pitfall 2: WebSocket Connections Drop Under Traefik
**What goes wrong:** WebSocket connections close after ~60 seconds during long-running tasks.
**Why it happens:** Traefik default transport timeout is 30s. Gzip compression middleware buffers WebSocket frames.
**How to avoid:** In Coolify's Traefik config, do NOT apply gzip middleware to the WebSocket route. The app already has 25s heartbeat pings (Phase 8 decision). Ensure Traefik's transport respondingTimeouts is set high enough (300s+).
**Warning signs:** WebSocket disconnects exactly at timeout boundary, client auto-reconnects repeatedly.

### Pitfall 3: PostgreSQL Connection Refused
**What goes wrong:** App container cannot connect to the PostgreSQL container.
**Why it happens:** Containers on different Docker networks cannot communicate. The existing PostgreSQL runs on the `coolify` network.
**How to avoid:** Ensure the app container joins the same Docker network as PostgreSQL, or use Coolify's internal DNS. The DATABASE_URL must use the container name (`ihhyb2rjq8jsx0ltbn1btj5a` or a stable alias) not `localhost`.
**Warning signs:** `asyncpg.exceptions.ConnectionRefusedError` on startup.

### Pitfall 4: Existing PostgreSQL Already Used by n8n
**What goes wrong:** Using the n8n PostgreSQL instance (user: n8n, db: n8n) for the agent console corrupts data.
**Why it happens:** The existing PostgreSQL container is configured for n8n exclusively.
**How to avoid:** Create a SEPARATE PostgreSQL database/user on the existing instance, OR deploy a second PostgreSQL container via Coolify dedicated to the agent console. The second option is cleaner.
**Warning signs:** Table conflicts, data from wrong application.

### Pitfall 5: Image Too Large / Slow Builds
**What goes wrong:** Docker image is 2GB+, builds take 10+ minutes.
**Why it happens:** Including unnecessary dev dependencies, not cleaning apt cache, not using .dockerignore.
**How to avoid:** Use .dockerignore to exclude `.git/`, `tests/`, `.planning/`, `docs/`, `__pycache__/`. Clean apt lists after install. Don't install dev dependencies.
**Warning signs:** Build takes more than 3-4 minutes, image exceeds 800MB.

### Pitfall 6: Port 8000 Conflict with Coolify Dashboard
**What goes wrong:** The app listens on port 8000, same as Coolify dashboard's host-mapped port.
**Why it happens:** Coolify maps its own dashboard to host port 8000 (`0.0.0.0:8000->8080/tcp`).
**How to avoid:** Do NOT map the container's port 8000 to the host. Traefik routes traffic by hostname, not port. The container port 8000 is internal-only, accessed via Traefik's Docker provider. No host port mapping needed.
**Warning signs:** Port already in use error on container start.

## Code Examples

### Dockerfile (verified pattern)
```dockerfile
FROM python:3.12-slim

# System deps + Node.js for Claude CLI
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl git ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Claude CLI
RUN npm install -g @anthropic-ai/claude-code

WORKDIR /app

# Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY pyproject.toml .
COPY src/ ./src/

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.server.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

### .dockerignore
```
.git/
.planning/
docs/
tests/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
.env
README.md
pytest.ini
```

### Uvicorn Factory Invocation
The app uses a factory pattern (`create_app()`), so uvicorn must be called with `--factory`:
```bash
python -m uvicorn src.server.app:create_app --factory --host 0.0.0.0 --port 8000
```

### Database Considerations
The existing PostgreSQL on the VPS is dedicated to n8n (user: n8n, db: n8n). The agent console needs its own database. Two options:

**Option A (Recommended): New PostgreSQL via Coolify**
Deploy a second PostgreSQL 16 instance through Coolify. Keeps databases isolated. Coolify handles it automatically.

**Option B: Shared PostgreSQL instance**
Create a new database and user on the existing PostgreSQL container:
```sql
CREATE USER agent_console WITH PASSWORD '<password>';
CREATE DATABASE agent_console OWNER agent_console;
```
Risk: shares resources with n8n, single point of failure.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Traefik v2 websocket | Traefik v3.6 native WebSocket | v3.0 (2024) | No special middleware needed for WS upgrade |
| Coolify v3 | Coolify v4 beta | 2024-2025 | New UI, better GitHub integration, different label format |
| docker-compose deploy | Coolify GitHub source | v4 | Push to GitHub triggers auto-build and deploy |

## Open Questions

1. **Dedicated PostgreSQL or shared instance?**
   - What we know: Existing PG is n8n's. App needs its own DB.
   - Recommendation: Deploy a second PostgreSQL 16 via Coolify (Option A). RAM cost is ~50-100MB which is acceptable given 1.6GB available.

2. **Claude CLI version pinning in Docker**
   - What we know: Host runs v2.1.74, `npm install -g @anthropic-ai/claude-code` installs latest.
   - Recommendation: Pin version in Dockerfile: `npm install -g @anthropic-ai/claude-code@2.1.74` for reproducibility. Update intentionally.

3. **Project workspace path inside container**
   - What we know: `APP_PROJECT_PATH` defaults to `.` (cwd). Agents operate on files in this path.
   - Recommendation: Mount a host directory (e.g., `~/projects/workspace`) to `/workspace` and set `APP_PROJECT_PATH=/workspace`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio |
| Config file | `pytest.ini` |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFR-03a | Docker image builds successfully | smoke | `docker build -t agent-console .` | No -- Wave 0 |
| INFR-03b | Container starts and health check passes | smoke | `docker run --rm -p 8001:8000 agent-console & sleep 5 && curl localhost:8001/health` | No -- Wave 0 |
| INFR-03c | Claude CLI available inside container | smoke | `docker run --rm agent-console claude --version` | No -- Wave 0 |
| INFR-03d | Coolify auto-deploy from GitHub | manual-only | Verify in Coolify UI after push | N/A -- manual |
| INFR-03e | HTTPS access at console.amcsystem.uk | manual-only | `curl -s https://console.amcsystem.uk/health` | N/A -- manual |
| INFR-03f | WebSocket survives long tasks | manual-only | Connect WS, run task, verify no disconnect | N/A -- manual |

### Sampling Rate
- **Per task commit:** `docker build -t agent-console . && docker run --rm agent-console claude --version`
- **Per wave merge:** Full build + health check test
- **Phase gate:** Container running on Coolify, HTTPS accessible, health check green

### Wave 0 Gaps
- [ ] `Dockerfile` -- the primary deliverable
- [ ] `.dockerignore` -- exclude dev files from build context
- [ ] Coolify application configuration (manual via UI, documented in plan)

## Sources

### Primary (HIGH confidence)
- Live VPS inspection: Docker containers, Traefik labels, network topology, PostgreSQL config
- Project source code: `src/server/app.py`, `src/server/config.py`, `src/runner/runner.py`
- Host environment: Python 3.12.3, Node.js 22.22.1, Claude CLI 2.1.74

### Secondary (MEDIUM confidence)
- Traefik v3 WebSocket handling (from Traefik docs -- native upgrade support)
- Coolify v4 GitHub deployment workflow (from Coolify documentation)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - verified from live VPS inspection of running containers
- Architecture: HIGH - based on actual Traefik labels and Coolify patterns observed on running services
- Pitfalls: HIGH - derived from actual infrastructure constraints (port conflicts, network isolation, shared PG)

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable infrastructure, unlikely to change)
