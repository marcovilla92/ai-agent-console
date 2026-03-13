"""Tests for context assembly helpers: assemble_full_context() and suggest_next_phase()."""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.context.assembler import (
    MAX_CONTEXT_CHARS,
    MAX_CLAUDE_MD_CHARS,
    MAX_PLANNING_DOC_CHARS,
    read_file_truncated,
    get_recent_git_log,
    get_recent_tasks,
    assemble_full_context,
    suggest_next_phase,
)


# ---------------------------------------------------------------------------
# read_file_truncated
# ---------------------------------------------------------------------------

class TestReadFileTruncated:
    def test_reads_file_content(self, tmp_path):
        (tmp_path / "hello.txt").write_text("hello world")
        result = read_file_truncated(str(tmp_path), "hello.txt", 1000)
        assert result == "hello world"

    def test_truncates_at_limit(self, tmp_path):
        (tmp_path / "big.txt").write_text("A" * 500)
        result = read_file_truncated(str(tmp_path), "big.txt", 100)
        assert len(result) <= 100 + len("\n...[truncated]")
        assert result.endswith("\n...[truncated]")
        assert result.startswith("A" * 100)

    def test_returns_empty_for_missing_file(self, tmp_path):
        result = read_file_truncated(str(tmp_path), "nonexistent.md", 1000)
        assert result == ""

    def test_encoding_errors_replaced(self, tmp_path):
        # Write bytes with invalid UTF-8
        (tmp_path / "bad.txt").write_bytes(b"hello \xff\xfe world")
        result = read_file_truncated(str(tmp_path), "bad.txt", 1000)
        assert "hello" in result
        assert result  # Should not crash


# ---------------------------------------------------------------------------
# get_recent_git_log
# ---------------------------------------------------------------------------

class TestGetRecentGitLog:
    @pytest.mark.asyncio
    async def test_returns_git_log_output(self, tmp_path):
        # Create a real git repo with a commit
        (tmp_path / ".git").mkdir()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"abc1234 initial commit\n", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await get_recent_git_log(str(tmp_path), count=5)
        assert "abc1234" in result

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_git_dir(self, tmp_path):
        result = await get_recent_git_log(str(tmp_path))
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_on_timeout(self, tmp_path):
        (tmp_path / ".git").mkdir()

        async def slow_communicate():
            await asyncio.sleep(10)
            return (b"", b"")

        mock_proc = AsyncMock()
        mock_proc.communicate = slow_communicate
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                result = await get_recent_git_log(str(tmp_path))
        assert result == ""


# ---------------------------------------------------------------------------
# get_recent_tasks
# ---------------------------------------------------------------------------

class TestGetRecentTasks:
    @pytest.mark.asyncio
    async def test_returns_task_dicts(self):
        now = datetime(2026, 3, 13, 12, 0, 0)
        mock_pool = AsyncMock()
        mock_pool.fetch.return_value = [
            {"id": 1, "prompt": "Do something", "status": "completed", "created_at": now},
            {"id": 2, "prompt": "Another task", "status": "running", "created_at": now},
        ]

        result = await get_recent_tasks(mock_pool, "/some/path", limit=5)
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["status"] == "completed"
        assert "prompt" in result[0]
        assert "created_at" in result[0]

    @pytest.mark.asyncio
    async def test_truncates_long_prompts(self):
        now = datetime(2026, 3, 13, 12, 0, 0)
        long_prompt = "X" * 500
        mock_pool = AsyncMock()
        mock_pool.fetch.return_value = [
            {"id": 1, "prompt": long_prompt, "status": "done", "created_at": now},
        ]

        result = await get_recent_tasks(mock_pool, "/path", limit=5)
        assert len(result[0]["prompt"]) <= 200

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_tasks(self):
        mock_pool = AsyncMock()
        mock_pool.fetch.return_value = []

        result = await get_recent_tasks(mock_pool, "/path")
        assert result == []


# ---------------------------------------------------------------------------
# assemble_full_context
# ---------------------------------------------------------------------------

class TestAssembleFullContext:
    @pytest.mark.asyncio
    async def test_returns_dict_with_five_keys(self, tmp_path):
        mock_pool = AsyncMock()
        mock_pool.fetch.return_value = []

        (tmp_path / ".git").mkdir()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"abc1234 commit msg\n", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await assemble_full_context(str(tmp_path), mock_pool)

        assert set(result.keys()) == {"workspace", "claude_md", "planning_docs", "git_log", "recent_tasks"}

    @pytest.mark.asyncio
    async def test_reads_claude_md_with_limit(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("C" * 5000)
        mock_pool = AsyncMock()
        mock_pool.fetch.return_value = []

        with patch("asyncio.create_subprocess_exec", AsyncMock()):
            result = await assemble_full_context(str(tmp_path), mock_pool)

        assert len(result["claude_md"]) <= MAX_CLAUDE_MD_CHARS + len("\n...[truncated]")

    @pytest.mark.asyncio
    async def test_reads_planning_docs_with_limit(self, tmp_path):
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "PROJECT.md").write_text("P" * 1000)
        (planning / "STATE.md").write_text("S" * 1000)
        (planning / "ROADMAP.md").write_text("R" * 1000)
        (planning / "REQUIREMENTS.md").write_text("Q" * 1000)

        mock_pool = AsyncMock()
        mock_pool.fetch.return_value = []

        with patch("asyncio.create_subprocess_exec", AsyncMock()):
            result = await assemble_full_context(str(tmp_path), mock_pool)

        # Each planning doc should be truncated to 500 chars
        for doc_content in result["planning_docs"].values():
            assert len(doc_content) <= MAX_PLANNING_DOC_CHARS + len("\n...[truncated]")

    @pytest.mark.asyncio
    async def test_skips_missing_planning_dir(self, tmp_path):
        mock_pool = AsyncMock()
        mock_pool.fetch.return_value = []

        with patch("asyncio.create_subprocess_exec", AsyncMock()):
            result = await assemble_full_context(str(tmp_path), mock_pool)

        assert result["planning_docs"] == {}

    @pytest.mark.asyncio
    async def test_total_context_within_limit(self, tmp_path):
        # Create large files to test budget
        (tmp_path / "CLAUDE.md").write_text("C" * 5000)
        planning = tmp_path / ".planning"
        planning.mkdir()
        for name in ["PROJECT.md", "STATE.md", "ROADMAP.md", "REQUIREMENTS.md"]:
            (planning / name).write_text("X" * 2000)

        mock_pool = AsyncMock()
        mock_pool.fetch.return_value = []

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"log line\n" * 20, b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await assemble_full_context(str(tmp_path), mock_pool)

        # Sum all text content
        total = len(result["workspace"]) + len(result["claude_md"]) + len(result["git_log"])
        total += sum(len(v) for v in result["planning_docs"].values())
        total += sum(len(str(t)) for t in result["recent_tasks"])
        # Individual limits budget to roughly 6000 chars
        assert total <= MAX_CONTEXT_CHARS + 2000  # workspace context can vary


# ---------------------------------------------------------------------------
# suggest_next_phase
# ---------------------------------------------------------------------------

SAMPLE_ROADMAP = """\
# Roadmap

### v2.1 Project Router

- [x] **Phase 12: DB Foundation** - Projects table
- [x] **Phase 13: Template System** - Template CRUD
- [ ] **Phase 14: Context Assembly** - Context aggregator
- [ ] **Phase 15: Project Service** - Project CRUD
- [ ] **Phase 16: Task Integration** - Task-project link
- [ ] **Phase 17: SPA Frontend** - Alpine.js app
"""

SAMPLE_STATE = """\
---
status: executing
---

# Project State

## Current Position

Phase: 14 of 17 (Context Assembly)
Plan: 01 of 02
"""

SAMPLE_STATE_PHASE_13 = """\
---
status: executing
---

# Project State

## Current Position

Phase: 13 of 17 (Template System)
Plan: 02 of 02
"""


class TestSuggestNextPhase:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_planning_dir(self, tmp_path):
        result = await suggest_next_phase(str(tmp_path))
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_roadmap(self, tmp_path):
        (tmp_path / ".planning").mkdir()
        result = await suggest_next_phase(str(tmp_path))
        assert result is None

    @pytest.mark.asyncio
    async def test_identifies_first_incomplete_phase(self, tmp_path):
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "ROADMAP.md").write_text(SAMPLE_ROADMAP)
        (planning / "STATE.md").write_text(SAMPLE_STATE)

        result = await suggest_next_phase(str(tmp_path))
        assert result is not None
        assert result["suggestion"] is not None
        assert result["suggestion"]["phase_id"] == "14"
        assert "Context Assembly" in result["suggestion"]["phase_name"]

    @pytest.mark.asyncio
    async def test_all_phases_populated(self, tmp_path):
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "ROADMAP.md").write_text(SAMPLE_ROADMAP)
        (planning / "STATE.md").write_text(SAMPLE_STATE)

        result = await suggest_next_phase(str(tmp_path))
        assert len(result["all_phases"]) == 6
        # First two should be complete
        assert result["all_phases"][0]["status"] == "complete"
        assert result["all_phases"][1]["status"] == "complete"

    @pytest.mark.asyncio
    async def test_detects_in_progress_from_state(self, tmp_path):
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "ROADMAP.md").write_text(SAMPLE_ROADMAP)
        (planning / "STATE.md").write_text(SAMPLE_STATE)

        result = await suggest_next_phase(str(tmp_path))
        # Phase 14 should be in_progress since STATE.md says Phase: 14
        phase_14 = [p for p in result["all_phases"] if p["phase_id"] == "14"][0]
        assert phase_14["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_all_complete_returns_none_suggestion(self, tmp_path):
        planning = tmp_path / ".planning"
        planning.mkdir()
        all_complete = """\
# Roadmap
- [x] **Phase 12: DB Foundation** - Done
- [x] **Phase 13: Template System** - Done
"""
        (planning / "ROADMAP.md").write_text(all_complete)

        result = await suggest_next_phase(str(tmp_path))
        assert result is not None
        assert result["suggestion"] is None
        assert len(result["all_phases"]) == 2

    @pytest.mark.asyncio
    async def test_suggestion_has_required_fields(self, tmp_path):
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "ROADMAP.md").write_text(SAMPLE_ROADMAP)
        (planning / "STATE.md").write_text(SAMPLE_STATE)

        result = await suggest_next_phase(str(tmp_path))
        suggestion = result["suggestion"]
        assert "phase_id" in suggestion
        assert "phase_name" in suggestion
        assert "status" in suggestion
        assert "reason" in suggestion
