# Phase 9: Approval Gates - Research

**Researched:** 2026-03-12
**Domain:** asyncio event-driven approval workflow, REST+WebSocket coordination
**Confidence:** HIGH

## Summary

Phase 9 implements approval gates for supervised mode tasks. The architecture is already well-prepared: `WebTaskContext` has `confirm_reroute()` and `handle_halt()` methods that currently auto-approve, the `TaskContext` Protocol defines these interfaces, and the WebSocket infrastructure from Phase 8 provides real-time communication. The `mode` field is already persisted per task.

The core pattern is straightforward: use `asyncio.Event` to pause the orchestrator pipeline when in supervised mode, broadcast an `approval_required` WebSocket event with context, expose a REST endpoint to submit the approval/rejection decision, and set the event to resume execution. This was already identified as the approach in STATE.md decisions: "asyncio.Event for supervised approval gates."

**Primary recommendation:** Add an `asyncio.Event` per pending approval to `WebTaskContext`, modify `confirm_reroute()` and `handle_halt()` to await this event when `mode == "supervised"`, add a `send_approval_required()` method to `ConnectionManager`, add a `POST /tasks/{id}/approve` REST endpoint, and wire `TaskManager` to relay the decision. No new dependencies needed -- this is pure asyncio + FastAPI.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TASK-04 | User can approve or reject agent actions via approval gate UI with context | asyncio.Event pause/resume pattern in WebTaskContext, approval_required WS event, POST /tasks/{id}/approve REST endpoint, context payload in approval request |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncio | stdlib | Event-based pause/resume for approval gates | Already used throughout; `asyncio.Event` is the canonical pattern for coroutine signaling |
| FastAPI | existing | REST endpoint for approve/reject | Already in stack |
| Pydantic | existing | Request/response models for approval endpoint | Already in stack |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncpg | existing | Persist approval decisions to DB | Already in stack for all DB ops |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| asyncio.Event | asyncio.Queue | Queue is overkill for single approve/reject; Event is simpler |
| In-memory pending map | Redis | Redis adds infra complexity; single-process model makes in-memory safe |

**Installation:**
```bash
# No new packages needed. All dependencies already installed.
```

## Architecture Patterns

### Recommended Changes
```
src/
├── engine/
│   └── context.py         # MODIFY: Add asyncio.Event approval gate logic
├── server/
│   ├── connection_manager.py  # MODIFY: Add send_approval_required()
│   └── routers/
│       └── tasks.py        # MODIFY: Add POST /tasks/{id}/approve endpoint
├── engine/
│   └── manager.py          # MODIFY: Add approve() method to relay decisions
└── db/
    └── pg_schema.py        # OPTIONAL: Add approval_events table if persistence needed
```

### Pattern 1: asyncio.Event Approval Gate
**What:** When `mode == "supervised"`, `confirm_reroute()` and `handle_halt()` create an `asyncio.Event`, broadcast an `approval_required` WebSocket message, then `await event.wait()`. A REST endpoint sets the event with the user's decision.
**When to use:** Every time the orchestrator asks for user confirmation in supervised mode.
**Example:**
```python
# In WebTaskContext
class WebTaskContext:
    def __init__(self, ...):
        ...
        self._approval_event: asyncio.Event | None = None
        self._approval_decision: str | None = None

    async def confirm_reroute(self, next_agent: str, reasoning: str) -> bool:
        if self._mode != "supervised":
            return True  # Auto-approve in autonomous mode

        # Broadcast approval request via WebSocket
        if self._connection_manager:
            await self._connection_manager.send_approval_required(
                self._task_id,
                action="reroute",
                context={"next_agent": next_agent, "reasoning": reasoning},
            )

        # Wait for user decision
        self._approval_event = asyncio.Event()
        await self._approval_event.wait()
        self._approval_event = None

        return self._approval_decision == "approve"

    def set_approval(self, decision: str) -> None:
        """Called by TaskManager when REST endpoint receives decision."""
        self._approval_decision = decision
        if self._approval_event:
            self._approval_event.set()
```

### Pattern 2: Approval REST Endpoint
**What:** `POST /tasks/{task_id}/approve` accepts `{"decision": "approve"|"reject"}` and relays to the running task's context.
**When to use:** User clicks approve/reject in the UI.
**Example:**
```python
class ApprovalRequest(BaseModel):
    decision: str  # "approve" or "reject"

@task_router.post("/{task_id}/approve")
async def approve_task(
    task_id: int,
    body: ApprovalRequest,
    manager: TaskManager = Depends(get_task_manager),
):
    success = await manager.approve(task_id, body.decision)
    if not success:
        raise HTTPException(404, "Task not found or not awaiting approval")
    return {"status": "ok", "decision": body.decision}
```

### Pattern 3: WebSocket Approval Event
**What:** A new message type `{"type": "approval_required", "data": {...}}` is broadcast to connected clients when approval is needed.
**When to use:** The orchestrator hits a decision point in supervised mode.
**Example:**
```python
# ConnectionManager addition
async def send_approval_required(
    self, task_id: int, action: str, context: dict
) -> None:
    await self._broadcast(task_id, {
        "type": "approval_required",
        "data": {
            "action": action,  # "reroute" or "halt"
            "context": context,
            # e.g. {"next_agent": "execute", "reasoning": "Code needs changes"}
        },
    })
```

### Pattern 4: Task Status Transition
**What:** Task status changes to `"awaiting_approval"` when paused at an approval gate, and back to `"running"` when approved/rejected.
**When to use:** Keeps the task list accurate for the dashboard (Phase 10).
**Example:**
```python
# In WebTaskContext.confirm_reroute / handle_halt:
# Before waiting:
await self._repo.update_status(self._task_id, "awaiting_approval")
if self._connection_manager:
    await self._connection_manager.send_status(self._task_id, "awaiting_approval")

# After decision received:
await self._repo.update_status(self._task_id, "running")
```

### Anti-Patterns to Avoid
- **Polling for approval:** Never have the orchestrator poll a DB flag. Use `asyncio.Event.wait()` which is zero-cost when waiting.
- **Separate approval process:** Do not create a separate asyncio.Task for approval handling. The approval gate lives inside the existing orchestration coroutine.
- **Timeout on approval wait:** Do not add arbitrary timeouts to approval waits. Users may take minutes to review. The task cancellation mechanism already handles abandoned tasks.
- **Storing approval state in DB only:** The in-memory `asyncio.Event` is the source of truth for the running coroutine. DB records are for auditing, not for signaling.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Coroutine synchronization | Custom flag + sleep loop | `asyncio.Event` | Built-in, zero-cost wait, thread-safe in asyncio context |
| Request validation | Manual field checks | Pydantic `BaseModel` with `Literal["approve", "reject"]` | Automatic validation, 422 on bad input |
| Real-time notification | HTTP polling | Existing WebSocket broadcast | Already built in Phase 8, zero additional infra |

**Key insight:** The entire approval gate mechanism is a coordination problem between two coroutines (the orchestration loop and the HTTP request handler) running in the same asyncio event loop. `asyncio.Event` is the textbook solution.

## Common Pitfalls

### Pitfall 1: Race Condition on Task Completion
**What goes wrong:** User sends approve/reject after the task has already completed, failed, or been cancelled.
**Why it happens:** The orchestration loop may finish between the user seeing the approval request and clicking the button.
**How to avoid:** Check that the task is still in `_running` AND has an active `_approval_event` before setting the decision. Return 409 Conflict if not awaiting approval.
**Warning signs:** Intermittent "Task not found" errors on the approve endpoint.

### Pitfall 2: Orphaned Approval Waits
**What goes wrong:** Task is cancelled while awaiting approval, but the `asyncio.Event` is never set, leaving a dangling coroutine.
**Why it happens:** `TaskManager.cancel()` cancels the asyncio.Task, which raises `CancelledError` in the `await event.wait()` call.
**How to avoid:** This is actually handled automatically -- `CancelledError` propagates through `event.wait()` and up through the orchestration loop to the `except CancelledError` handler in `TaskManager._execute`. No special handling needed, but verify in tests.
**Warning signs:** Tasks stuck in "awaiting_approval" status after cancellation.

### Pitfall 3: Multiple Approval Requests Before Response
**What goes wrong:** The orchestrator could theoretically hit two approval points before the user responds to the first.
**Why it happens:** It cannot actually happen -- the orchestrator is sequential (one agent at a time), and it awaits the approval before proceeding. But a developer might try to "optimize" by making approval non-blocking.
**How to avoid:** Keep the sequential nature. One approval at a time per task. The `_approval_event` field being singular (not a queue) enforces this.
**Warning signs:** N/A -- this is a design principle, not a runtime issue.

### Pitfall 4: WebTaskContext Reference Mismatch
**What goes wrong:** `TaskManager` has two `WebTaskContext` instances per task -- one created in `submit()` and one in `_execute()`. The REST endpoint must reach the one inside `_execute()` (the one the orchestrator actually uses).
**Why it happens:** Current code already handles this -- `_execute()` updates `self._running[task_id].ctx` after creating the new context.
**How to avoid:** Route `approve()` through `self._running[task_id].ctx` which points to the correct context.
**Warning signs:** Approval seems to work but the orchestrator doesn't resume.

## Code Examples

### Complete WebTaskContext Approval Flow
```python
# Source: Derived from existing codebase patterns

async def confirm_reroute(self, next_agent: str, reasoning: str) -> bool:
    """Confirm re-routing. Pauses for approval in supervised mode."""
    if self._mode != "supervised":
        log.debug("auto-approve reroute (autonomous): next=%s", next_agent)
        return True

    log.info("approval gate: reroute next=%s reasoning=%s", next_agent, reasoning)

    # Update status to awaiting_approval
    repo = TaskRepository(self._pool)
    await repo.update_status(self._task_id, "awaiting_approval")

    # Broadcast approval request
    if self._connection_manager:
        await self._connection_manager.send_approval_required(
            self._task_id,
            action="reroute",
            context={"next_agent": next_agent, "reasoning": reasoning},
        )
        await self._connection_manager.send_status(
            self._task_id, "awaiting_approval"
        )

    # Wait for user decision
    self._approval_event = asyncio.Event()
    self._approval_decision = None
    await self._approval_event.wait()
    self._approval_event = None

    # Resume running
    await repo.update_status(self._task_id, "running")
    if self._connection_manager:
        await self._connection_manager.send_status(self._task_id, "running")

    decision = self._approval_decision
    log.info("approval gate resolved: decision=%s", decision)
    return decision == "approve"
```

### TaskManager.approve()
```python
async def approve(self, task_id: int, decision: str) -> bool:
    """Relay approval/rejection decision to a running task.

    Returns True if the task was awaiting approval and the decision was set.
    """
    running = self._running.get(task_id)
    if running is None:
        return False

    ctx = running.ctx
    if ctx._approval_event is None or ctx._approval_event.is_set():
        return False

    ctx.set_approval(decision)
    return True
```

### WebSocket Message Types (Updated)
```python
# Existing types from Phase 8:
{"type": "chunk", "data": "output text..."}
{"type": "status", "data": "running|completed|failed|cancelled|awaiting_approval"}
{"type": "ping"}

# New type for Phase 9:
{
    "type": "approval_required",
    "data": {
        "action": "reroute",      # or "halt"
        "context": {
            "next_agent": "execute",
            "reasoning": "Code needs changes based on review feedback",
            # For halt: "iteration_count": 3
        }
    }
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Auto-approve all (Phase 7) | Event-based approval gate | Phase 9 | Users get control over agent actions in supervised mode |
| No awaiting_approval status | Task status includes awaiting_approval | Phase 9 | Dashboard can show tasks waiting for user input |

**Deprecated/outdated:**
- The TUI `confirm_reroute`/`handle_halt` pattern (modal dialogs) is the v1.0 equivalent. The web version uses async events + REST instead of modal screens.

## Open Questions

1. **Should approval decisions be persisted to a DB table?**
   - What we know: Orchestrator decisions are already logged in `orchestrator_decisions` table. Approval decisions are a different concern (user input, not AI routing).
   - What's unclear: Whether a separate `approval_events` table adds value for this single-user system.
   - Recommendation: Skip DB persistence for approvals in Phase 9. The task status transitions are already logged. Add a table later if audit requirements emerge.

2. **Should handle_halt offer "continue" option via REST?**
   - What we know: TUI `HaltDialog` returns "continue", "approve", or "stop". The REST endpoint only needs "approve" or "reject", but "continue" (reset iteration counter and keep going) is a third option.
   - What's unclear: Whether the REST API should expose all three options.
   - Recommendation: Support all three: `{"decision": "approve"|"reject"|"continue"}`. Map "reject" to "stop" internally. This preserves parity with the TUI.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pyproject.toml / pytest section |
| Quick run command | `cd /home/ubuntu/projects/ai-agent-console && python -m pytest tests/test_task_manager.py tests/test_task_endpoints.py -x -q` |
| Full suite command | `cd /home/ubuntu/projects/ai-agent-console && python -m pytest tests/ -x -q` |

### Phase Requirements - Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TASK-04a | Supervised mode pauses at reroute, sends approval_required WS event | unit | `python -m pytest tests/test_task_manager.py::test_supervised_pauses_at_reroute -x` | No -- Wave 0 |
| TASK-04b | Approve via REST resumes execution | integration | `python -m pytest tests/test_task_endpoints.py::test_approve_resumes_task -x` | No -- Wave 0 |
| TASK-04c | Reject via REST stops execution | integration | `python -m pytest tests/test_task_endpoints.py::test_reject_stops_task -x` | No -- Wave 0 |
| TASK-04d | Approval request includes action context | unit | `python -m pytest tests/test_task_manager.py::test_approval_includes_context -x` | No -- Wave 0 |
| TASK-04e | Autonomous mode runs without pausing | unit | `python -m pytest tests/test_task_manager.py::test_autonomous_no_pause -x` | No -- Wave 0 |
| TASK-04f | Cancel while awaiting approval works | unit | `python -m pytest tests/test_task_manager.py::test_cancel_while_awaiting -x` | No -- Wave 0 |
| TASK-04g | Approve non-existent/non-waiting task returns error | integration | `python -m pytest tests/test_task_endpoints.py::test_approve_not_awaiting -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_task_manager.py tests/test_task_endpoints.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_task_manager.py` -- add approval gate unit tests (supervised pause, autonomous skip, cancel while awaiting)
- [ ] `tests/test_task_endpoints.py` -- add approval REST endpoint integration tests (approve, reject, not-awaiting error)
- [ ] No new framework install needed -- pytest + pytest-asyncio already configured

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `src/engine/context.py`, `src/engine/manager.py`, `src/pipeline/orchestrator.py`, `src/pipeline/protocol.py` -- current approval interface and auto-approve stubs
- Codebase analysis: `src/server/connection_manager.py`, `src/server/routers/ws.py`, `src/server/routers/tasks.py` -- WebSocket and REST infrastructure
- Python stdlib docs: `asyncio.Event` -- coroutine synchronization primitive
- STATE.md decision: "asyncio.Event for supervised approval gates" -- pre-decided approach

### Secondary (MEDIUM confidence)
- Codebase analysis: `src/tui/task_context.py` -- TUI approval pattern (modal dialogs) as reference for web equivalent

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all asyncio stdlib + existing FastAPI
- Architecture: HIGH - pattern is pre-decided (asyncio.Event), interfaces already exist (TaskContext Protocol), stubs already in place (auto-approve methods)
- Pitfalls: HIGH - derived from direct codebase analysis (dual context reference, cancellation flow, race conditions)

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (stable -- no external dependencies changing)
