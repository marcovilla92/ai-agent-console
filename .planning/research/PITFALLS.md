# Pitfalls Research

**Domain:** TUI-to-Web migration -- FastAPI + WebSocket + Docker + Claude CLI subprocess
**Researched:** 2026-03-12
**Confidence:** HIGH (verified across official docs, GitHub issues, and community reports)

## Critical Pitfalls

### Pitfall 1: Claude CLI Auth Lost on Container Restart

**What goes wrong:**
Claude CLI inside Docker loses authentication every time the container restarts or redeploys. The app starts, tries to spawn `claude -p`, and gets an auth error. Every Coolify deploy breaks the system until someone manually re-authenticates.

**Why it happens:**
Claude CLI requires TWO files for persistent auth: `~/.claude/.credentials.json` AND `~/.claude.json`. Most developers only mount one. Additionally, Claude needs WRITE access to these files (it refreshes tokens), so read-only mounts silently fail. Using Claude on the host outside the container can also delete the credentials file (confirmed in GitHub issue #1736).

**How to avoid:**
1. Mount both paths read-write in docker-compose:
   ```yaml
   volumes:
     - /home/ubuntu/.claude:/home/appuser/.claude
     - /home/ubuntu/.claude.json:/home/appuser/.claude.json
   ```
2. Add an entrypoint script that verifies auth files exist and have correct ownership before starting FastAPI.
3. Set `CLAUDE_CONFIG_DIR` environment variable explicitly.
4. Add `"bypassPermissionsModeAccepted": true` to `.claude.json` since the app uses `--dangerously-skip-permissions`.
5. Never use Claude CLI from the host while the container is running -- keep credentials exclusive to one consumer.

**Warning signs:**
- `subprocess.CalledProcessError` with exit code 1 from `stream_claude` right after deploy
- Auth works once then fails after Coolify redeploy
- Works locally but fails in container

**Phase to address:**
Docker/deployment setup phase -- must be validated BEFORE any WebSocket or API work is deployed, since everything depends on Claude CLI functioning.

---

### Pitfall 2: Zombie Claude CLI Processes Exhaust VPS RAM

**What goes wrong:**
Claude CLI subprocesses (each consuming 200-500MB+ RAM) accumulate when WebSocket clients disconnect without proper cleanup. With only ~5GB available RAM and a 2-process semaphore, even 3-4 zombie processes push the VPS into OOM territory. The Linux OOM killer may kill the Docker daemon itself, taking down n8n and Evolution API alongside the agent console.

**Why it happens:**
The current `stream_claude` function (in `src/runner/runner.py`) awaits `proc.wait()` at the end, but if the calling coroutine is cancelled (WebSocket disconnect, client navigates away, network drop), the subprocess is never terminated. `asyncio.create_task` without stored references creates "fire and forget" tasks that cannot be cancelled during shutdown. FastAPI's `BackgroundTasks` are request-scoped but raw `asyncio.create_task` is not.

**How to avoid:**
1. Refactor `stream_claude` to accept a cancellation token or wrap every call in try/finally that terminates the subprocess:
   ```python
   try:
       async for chunk in stream_claude(prompt):
           await websocket.send_text(chunk)
   finally:
       if proc.returncode is None:
           proc.terminate()
           try:
               await asyncio.wait_for(proc.wait(), timeout=5.0)
           except asyncio.TimeoutError:
               proc.kill()
   ```
2. Maintain a registry of active subprocess PIDs. On shutdown (lifespan teardown), kill all remaining processes.
3. Set Docker memory limits (`mem_limit: 3g`) so OOM kills only the agent console container, not the entire host.
4. Add a periodic health check that counts child processes and logs warnings when approaching the semaphore limit.

**Warning signs:**
- `ps aux | grep claude` shows more processes than the semaphore limit allows
- Container memory usage climbs monotonically over time
- Other Coolify services (n8n, Evolution API) become unresponsive
- `dmesg | grep -i oom` shows OOM kills

**Phase to address:**
Core WebSocket streaming phase -- this is the FIRST thing to get right when wiring WebSocket to subprocess. Build the cleanup mechanism before building the streaming.

---

### Pitfall 3: WebSocket Connections Silently Die Behind Traefik

**What goes wrong:**
WebSocket connections appear established but stop receiving data. The client shows a connected state while the server-side coroutine is blocked or errored. Long-running Claude CLI tasks (5-30 minutes) exceed Traefik's default 60-second timeout, causing the proxy to drop the connection while the subprocess continues running.

**Why it happens:**
Three compounding issues: (1) Traefik's default `respondingTimeouts.readTimeout` is 60 seconds -- any pause longer than that in Claude CLI output kills the connection (confirmed in Coolify GitHub #5358). (2) Coolify's Gzip compression interferes with WebSocket streaming -- this is a confirmed bug (Coolify GitHub #4002), fix is disabling Gzip in advanced settings. (3) FastAPI does not propagate WebSocket disconnect state unless you explicitly call `websocket.receive_text()`, so the server keeps streaming to a dead connection (FastAPI GitHub #9031).

**How to avoid:**
1. Configure Traefik timeouts in Coolify server proxy settings:
   ```
   --entrypoints.https.transport.respondingTimeouts.readTimeout=30m
   --entrypoints.https.transport.respondingTimeouts.writeTimeout=30m
   --entrypoints.https.transport.respondingTimeouts.idleTimeout=30m
   ```
2. Disable Gzip compression in Coolify advanced settings for this application.
3. Implement server-side heartbeat: send a ping frame every 15 seconds over the WebSocket.
4. Run a concurrent `receive_text()` task alongside the streaming task to detect disconnects:
   ```python
   async def watch_disconnect(ws):
       try:
           while True:
               await ws.receive_text()
       except WebSocketDisconnect:
           return

   streaming_task = asyncio.create_task(stream_to_ws(ws, prompt))
   disconnect_task = asyncio.create_task(watch_disconnect(ws))
   done, pending = await asyncio.wait(
       [streaming_task, disconnect_task],
       return_when=asyncio.FIRST_COMPLETED,
   )
   for task in pending:
       task.cancel()
   ```

**Warning signs:**
- Client shows "connected" but no new data arrives after initial connection
- Server logs show successful sends after client has navigated away
- Tasks complete on server but client never receives the result
- Works locally but fails when deployed behind Coolify/Traefik

**Phase to address:**
WebSocket implementation phase -- build heartbeat and disconnect detection into the WebSocket handler from day one. Traefik configuration in deployment phase.

---

### Pitfall 4: asyncpg Pool Exhaustion Under Concurrent Tasks

**What goes wrong:**
Database operations start timing out or hanging. New WebSocket connections fail to save task records. The entire application becomes unresponsive even though Claude CLI processes are running fine.

**Why it happens:**
The current codebase uses a single `aiosqlite.Connection` shared across the app (see `src/db/repository.py`). Migrating to asyncpg requires a connection pool, but developers often: (1) set pool size too small or too large, (2) forget to release connections (missing `async with pool.acquire()` context manager), (3) hold connections during long-running operations (like waiting for Claude CLI to finish -- the current `log_decision` pattern acquires a connection, writes, and commits inline with the orchestration loop), or (4) create the pool outside the lifespan handler so it is not properly cleaned up on shutdown.

**How to avoid:**
1. Create pool in FastAPI lifespan, close in teardown:
   ```python
   @asynccontextmanager
   async def lifespan(app: FastAPI):
       app.state.db_pool = await asyncpg.create_pool(
           dsn=settings.database_url,
           min_size=2, max_size=5,
           max_inactive_connection_lifetime=300,
       )
       yield
       await app.state.db_pool.close()
   ```
2. Never hold a connection while awaiting a subprocess. Acquire, write, release. Then run subprocess. Then acquire again for the result.
3. Use `pool.acquire()` as async context manager everywhere -- never manually acquire without release.
4. Set `max_size=5` (not higher). Single-user app with 2 concurrent tasks needs at most 4-5 connections.
5. Connect to the EXISTING Coolify-managed PostgreSQL via Docker network, not localhost.

**Warning signs:**
- `asyncpg.exceptions.TooManyConnectionsError` in logs
- Requests hang for exactly the pool timeout duration then fail
- Database operations work initially but degrade after running several tasks

**Phase to address:**
Database migration phase -- must be correct from the start since every other feature depends on persistence.

---

### Pitfall 5: asyncio Task Lifecycle Mismatch with FastAPI Shutdown

**What goes wrong:**
Background tasks created with `asyncio.create_task()` continue running after the FastAPI app receives SIGTERM. Shutdown hangs for 30+ seconds (uvicorn's default graceful shutdown timeout). Or worse, tasks are abruptly killed mid-operation leaving database records in inconsistent states (task status stuck on "running" forever).

**Why it happens:**
The current orchestrator (`orchestrate_pipeline` in `src/pipeline/orchestrator.py`) is a long-running coroutine designed for a TUI lifetime -- it loops `while not state.halted and not state.approved` with no check for external cancellation signals. In FastAPI, it will be launched as a background task per WebSocket connection. FastAPI's lifespan shutdown does not automatically cancel arbitrary tasks created with `asyncio.create_task`.

**How to avoid:**
1. Create a `TaskManager` class that tracks all running orchestration tasks:
   ```python
   class TaskManager:
       def __init__(self):
           self._tasks: dict[str, asyncio.Task] = {}

       def register(self, task_id: str, task: asyncio.Task):
           self._tasks[task_id] = task
           task.add_done_callback(lambda t: self._tasks.pop(task_id, None))

       async def shutdown(self, timeout: float = 10.0):
           for task in self._tasks.values():
               task.cancel()
           await asyncio.gather(*self._tasks.values(), return_exceptions=True)
   ```
2. Register TaskManager in FastAPI lifespan -- call `task_manager.shutdown()` in teardown.
3. Add cancellation checks in the orchestration loop:
   ```python
   while not state.halted and not state.approved:
       await asyncio.sleep(0)  # yields to event loop, raises CancelledError if cancelled
       ...
   ```
4. Use `asyncio.shield()` around critical DB writes that must complete even during cancellation.
5. Add a "cancelled" / "interrupted" terminal state to task records so the UI shows accurate status.
6. On app startup, reconcile stale state: mark all "running" tasks as "interrupted".

**Warning signs:**
- Shutdown takes exactly `uvicorn --timeout-graceful-shutdown` seconds (default 30)
- Tasks show "running" in the database but no subprocess is active
- Container restart in Coolify takes abnormally long
- `docker logs` shows `Waiting for background tasks to complete...` during deploy

**Phase to address:**
Core API scaffolding phase -- the TaskManager pattern must be established before any orchestration logic is wired to WebSocket endpoints.

---

### Pitfall 6: Docker Network Isolation Blocks Access to Existing Services

**What goes wrong:**
The agent console container cannot reach the Coolify-managed PostgreSQL instance. Connection refused errors on `localhost:5432` because inside Docker, localhost is the container itself, not the host.

**Why it happens:**
Coolify manages services in its own Docker network (`coolify` network). A new application deployed via Coolify may be placed on a different network. Developers hardcode `localhost` or `127.0.0.1` as the database host from their local development experience.

**How to avoid:**
1. Use the Coolify-assigned internal hostname for PostgreSQL (visible in Coolify dashboard, usually a service name like `postgresql-xxxx`).
2. Ensure the agent console is on the same Docker network as the PostgreSQL service. In Coolify, configure this in the application's network settings.
3. Use environment variables for all connection strings, never hardcode:
   ```
   DATABASE_URL=postgresql://user:pass@postgresql-xxxx:5432/agent_console
   ```
4. Test connectivity from within the container: `docker exec <container> pg_isready -h <pg-hostname>`.
5. If networks cannot be shared, use `host.docker.internal` (Linux requires `--add-host=host.docker.internal:host-gateway`).

**Warning signs:**
- `Connection refused` on port 5432 from within the container
- Works with `docker-compose up` locally but fails in Coolify
- Can reach the database from the VPS host but not from the container

**Phase to address:**
Docker/deployment setup phase -- validate network connectivity before building any database-dependent features.

---

### Pitfall 7: WebSocket Message Buffer Overflow During Long Streams

**What goes wrong:**
Claude CLI produces `content_block_delta` events faster than the WebSocket can send them. Messages accumulate in memory, eventually causing the container to exhaust RAM or the WebSocket to fail silently.

**Why it happens:**
The current `stream_claude` yields every `content_block_delta` text chunk as fast as they arrive (see `src/runner/runner.py` line 88-92). When forwarded over WebSocket, network latency and client processing speed create backpressure that is not handled. Sending thousands of small messages in rapid succession without flow control causes buffer bloat.

**How to avoid:**
1. Batch small deltas before sending over WebSocket -- accumulate chunks and flush every 50ms or 1KB, whichever comes first:
   ```python
   buffer = []
   last_flush = time.monotonic()
   async for chunk in stream_claude(prompt):
       if isinstance(chunk, str):
           buffer.append(chunk)
           if time.monotonic() - last_flush > 0.05 or len("".join(buffer)) > 1024:
               await websocket.send_text(json.dumps({"type": "delta", "text": "".join(buffer)}))
               buffer.clear()
               last_flush = time.monotonic()
       elif isinstance(chunk, dict):  # result event
           if buffer:
               await websocket.send_text(json.dumps({"type": "delta", "text": "".join(buffer)}))
               buffer.clear()
           await websocket.send_text(json.dumps(chunk))
   ```
2. Monitor WebSocket send queue depth.
3. Use a bounded asyncio.Queue between the subprocess reader and WebSocket sender for backpressure.

**Warning signs:**
- Client receives large bursts of messages followed by silence
- Container memory spikes during streaming phases
- WebSocket connection drops mid-stream with no error on the server side

**Phase to address:**
WebSocket streaming phase -- implement buffering when first wiring `stream_claude` to WebSocket.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Single aiosqlite connection instead of asyncpg pool | No migration effort | Cannot handle concurrent writes, blocks event loop | Never in web version -- migrate immediately |
| Global `asyncio.Semaphore` without task tracking | Simple concurrency limit | Cannot cancel or inspect running tasks, zombie processes | Only for MVP; replace with TaskManager before production |
| Hardcoded `claude` binary path via `shutil.which` | Works on host | Fails in Docker if PATH differs or `claude` is in a non-standard location | MVP only; add explicit config/env var for container binary path |
| No WebSocket authentication | Faster development | Anyone on the network can connect and launch Claude tasks (Pro Max costs) | Never -- add Basic Auth to WebSocket handshake from day one |
| `--dangerously-skip-permissions` with broad volume mounts | Required for non-interactive use | Claude can modify any file the process has access to | Acceptable -- mitigate with narrow Docker volume constraints |
| Porting aiosqlite SQL to asyncpg with `?` placeholders | Copy-paste migration | asyncpg uses `$1, $2` not `?`; will crash at runtime | Never -- fix during migration, verified by tests |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Coolify + PostgreSQL | Using `localhost:5432` as DB host | Use Coolify service hostname on shared Docker network |
| Coolify + Traefik | Default 60s timeout kills long WebSocket connections | Set `respondingTimeouts.readTimeout=30m` in proxy config |
| Coolify + Traefik | Gzip compression breaks WebSocket/SSE | Disable Gzip in Coolify advanced settings for this app |
| Claude CLI + Docker | Mounting only `.credentials.json` | Must mount BOTH `~/.claude/` directory AND `~/.claude.json` file, read-write |
| Claude CLI + Docker | Running `claude` as root but auth files owned by host user | Use entrypoint script to fix file ownership with `chown` |
| asyncpg migration | Porting SQL queries 1:1 from aiosqlite | asyncpg uses `$1, $2` placeholders (not `?`), returns `Record` objects (not tuples), has no `.commit()` (autocommit by default) |
| FastAPI + long-running tasks | Using `BackgroundTasks` for multi-minute orchestration | Use `asyncio.create_task` with a TaskManager for lifecycle control |
| FastAPI WebSocket | Assuming disconnect is detected automatically | Must run concurrent `receive_text()` loop or heartbeat to detect disconnects |
| Docker + Claude CLI | Assuming `shutil.which("claude")` works in container | Claude CLI (npm package) needs Node.js in the container image; install globally and verify PATH |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Holding DB connection during subprocess wait | Pool exhaustion after 2-3 concurrent tasks | Acquire/release around each DB operation, not around task lifecycle | Immediately with 2+ concurrent tasks |
| No WebSocket message batching | RAM spikes during streaming, client lag | Buffer and flush every 50ms | With verbose Claude CLI output (large codebases) |
| Unbounded task history in memory | Slow response times after many tasks | Paginate task listing, keep only active tasks in memory | After 50-100 completed tasks |
| Logging full Claude CLI output to Docker stdout | Docker log storage fills 72GB disk | Log summaries only; store full output in PostgreSQL; configure Docker log rotation | After a few days of continuous operation |
| No Docker memory limit on container | OOM killer targets random process (could be n8n, Evolution API) | Set `mem_limit: 3g` on the container | First time 2 Claude processes produce large output simultaneously |
| Creating new DB connection per request instead of using pool | Connection overhead, PG max_connections reached | Use asyncpg pool via `app.state`, inject via dependency | After ~100 concurrent DB operations |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| No auth on WebSocket endpoint | Anyone can launch Claude tasks costing money (Pro Max subscription) | Add HTTP Basic Auth check during WebSocket handshake |
| Claude credentials baked into Docker image layer | Credentials leaked if image is pushed to registry | Mount at runtime via volumes, never COPY in Dockerfile |
| `--dangerously-skip-permissions` with unrestricted volume mounts | Claude can read/write any mounted directory including host system | Mount only specific workspace directories, never `/` or `/home` |
| SSH keys mounted for GitHub integration without restrictions | Claude subprocess could exfiltrate or misuse keys | Use deploy keys (read-only where possible), mount as read-only |
| No rate limiting on task creation API | Accidental or malicious spawn of many concurrent tasks | Enforce semaphore at API level, not just in orchestrator |
| Database password in plaintext environment variable | Visible in `docker inspect` and Coolify dashboard | Use Coolify's secret management; restrict dashboard access |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No late-join replay on WebSocket | Opening dashboard mid-task shows blank screen | Store stream chunks in memory ring buffer, replay on connect |
| No task status persistence across page loads | Browser refresh loses all context about running tasks | Write status updates to PostgreSQL, hydrate from DB on page load |
| Silent subprocess failure after timeout | User waits forever for output that will never come | Set subprocess timeout (e.g., 30 min), show error state in UI with elapsed time |
| Approval gate with no visible indicator | In supervised mode, user does not realize a task is waiting for approval | Show clear pending-approval badge; auto-scroll to approval prompt |
| No indication of queue position | User submits task when 2 are running, sees nothing happen | Show "queued (position N)" status while waiting for semaphore |
| WebSocket reconnect loses context | Network blip causes full page reload | Implement auto-reconnect with state recovery from server |

## "Looks Done But Isn't" Checklist

- [ ] **WebSocket streaming:** Often missing disconnect detection -- verify the server stops streaming AND kills subprocess when client disconnects
- [ ] **Claude CLI in Docker:** Often missing `.claude.json` mount -- verify auth survives a `docker restart`
- [ ] **Traefik proxy:** Often missing timeout config -- verify a 10-minute idle period does not drop the WebSocket connection
- [ ] **asyncpg pool:** Often missing lifespan teardown -- verify `pool.close()` is called on shutdown (check for connection leak warnings in logs)
- [ ] **Task cancellation:** Often missing subprocess cleanup -- verify `ps aux | grep claude` shows 0 processes after all tasks are stopped
- [ ] **Database migration:** Often missing placeholder syntax change -- verify no `?` placeholders remain (asyncpg uses `$1`)
- [ ] **Docker networking:** Often missing shared network -- verify container can reach PostgreSQL by Coolify hostname
- [ ] **Coolify Gzip setting:** Often left as default on -- verify Gzip is disabled for the WebSocket application
- [ ] **Docker memory limits:** Often unset -- verify `docker stats` shows a memory limit on the container
- [ ] **Graceful shutdown:** Often untested -- verify `docker stop` completes within 10 seconds with 2 running tasks
- [ ] **Startup reconciliation:** Often missing -- verify that tasks marked "running" before a crash are updated to "interrupted" on restart
- [ ] **Claude CLI PATH:** Often assumes host PATH -- verify `claude --version` works inside the container

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Zombie subprocess accumulation | LOW | `pkill -f "claude -p"` on host; restart container; add cleanup code |
| OOM kill of container only | LOW | Container auto-restarts via Coolify; add memory limits to prevent recurrence |
| OOM kill of Docker daemon | HIGH | SSH into VPS, `systemctl restart docker`, all Coolify services restart cold; add container memory limits to prevent |
| Database pool exhaustion | LOW | Restart FastAPI app; fix connection leak; reduce pool hold times |
| Auth credentials lost in container | LOW | Re-run `claude login` inside container; fix volume mounts to persist |
| Traefik zombie state | MEDIUM | Restart Traefik via Coolify dashboard; known Coolify bug #7744 |
| Inconsistent task state in DB | LOW | Add startup reconciliation: mark all "running" tasks as "interrupted" on app boot |
| Disk full from Docker logs | MEDIUM | `docker system prune`; add log rotation in `/etc/docker/daemon.json`; configure `max-size` and `max-file` |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Claude CLI auth in Docker | Docker/Deployment setup | `docker exec <c> claude --version` succeeds after container restart |
| Zombie subprocess accumulation | WebSocket streaming (core) | Kill WebSocket mid-stream, verify subprocess terminates within 10s |
| WebSocket dies behind Traefik | Deployment configuration | 10-minute idle WebSocket stays connected in production |
| asyncpg pool exhaustion | Database migration | Run 3 concurrent tasks, verify no pool timeout errors |
| Task lifecycle mismatch | Core API scaffolding | `docker stop` completes in under 10s with 2 running tasks |
| Docker network isolation | Docker/Deployment setup | App connects to existing PG from container on first boot |
| Message buffer overflow | WebSocket streaming | Stream a large codebase task, verify container RAM stays stable |
| aiosqlite-to-asyncpg syntax | Database migration | Full test suite passes with asyncpg (no `?` placeholders, no `.commit()`) |

## Sources

- [Claude Code Docker Auth Persistence (GitHub #1736)](https://github.com/anthropics/claude-code/issues/1736) -- HIGH confidence
- [Claude Code Credential Two-File Requirement (Field Notes #10)](https://github.com/tfvchow/field-notes-public/issues/10) -- HIGH confidence
- [Claude Code Development Containers (Official Docs)](https://code.claude.com/docs/en/devcontainer) -- HIGH confidence
- [Coolify WebSocket/SSE Bug with Gzip (GitHub #4002)](https://github.com/coollabsio/coolify/issues/4002) -- HIGH confidence
- [Coolify Traefik 60s Default Timeout (GitHub #5358)](https://github.com/coollabsio/coolify/issues/5358) -- HIGH confidence
- [Coolify Traefik Zombie State (GitHub #7744)](https://github.com/coollabsio/coolify/issues/7744) -- MEDIUM confidence
- [FastAPI WebSocket Disconnect Detection (GitHub #9031)](https://github.com/fastapi/fastapi/discussions/9031) -- HIGH confidence
- [FastAPI Async Task Pitfalls (Leapcell)](https://leapcell.io/blog/understanding-pitfalls-of-async-task-management-in-fastapi-requests) -- MEDIUM confidence
- [FastAPI Lifespan Events (Dev Central)](https://dev.turmansolutions.ai/2025/09/27/understanding-fastapis-lifespan-events-proper-initialization-and-shutdown/) -- MEDIUM confidence
- [asyncpg with FastAPI (Feldroy 2025)](https://daniel.feldroy.com/posts/2025-10-using-asyncpg-with-fastapi-and-air) -- MEDIUM confidence
- [Docker Resource Constraints (Official Docs)](https://docs.docker.com/engine/containers/resource_constraints/) -- HIGH confidence
- [Coolify Gateway Timeout Docs](https://coolify.io/docs/troubleshoot/applications/gateway-timeout) -- HIGH confidence

---
*Pitfalls research for: AI Agent Console v2.0 -- TUI to Web Platform migration*
*Researched: 2026-03-12*
