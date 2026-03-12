"""Tests for pipeline runner."""
from unittest.mock import AsyncMock, patch

import pytest

from src.pipeline.runner import run_pipeline, PipelineResult, PIPELINE_STEPS


PLAN_OUTPUT = """GOAL:
Build a REST API

TASKS:
1. Create endpoints

HANDOFF:
Execute should build the API.
"""

EXECUTE_OUTPUT = """TARGET:
REST API with CRUD

CODE:
```python
print("hello")
```

HANDOFF:
Review the code quality.
"""

REVIEW_OUTPUT = """SUMMARY:
Code implements a basic REST API.

ISSUES:
No issues found.

RISKS:
No significant risks.

IMPROVEMENTS:
Add input validation.

DECISION:
APPROVED -- Code is ready for use.
"""


@pytest.fixture
async def db_with_schema(db_conn):
    """db_conn from conftest already has schema."""
    return db_conn


async def test_pipeline_runs_three_steps(db_with_schema, tmp_path):
    with patch("src.agents.base.invoke_claude_with_retry", new_callable=AsyncMock) as mock:
        mock.side_effect = [PLAN_OUTPUT, EXECUTE_OUTPUT, REVIEW_OUTPUT]
        result = await run_pipeline("Build an API", str(tmp_path), db_with_schema)

    assert isinstance(result, PipelineResult)
    assert len(result.steps) == 3
    assert result.steps[0].agent_name == "plan"
    assert result.steps[1].agent_name == "execute"
    assert result.steps[2].agent_name == "review"


async def test_pipeline_creates_session(db_with_schema, tmp_path):
    with patch("src.agents.base.invoke_claude_with_retry", new_callable=AsyncMock) as mock:
        mock.side_effect = [PLAN_OUTPUT, EXECUTE_OUTPUT, REVIEW_OUTPUT]
        result = await run_pipeline("Build an API", str(tmp_path), db_with_schema)

    assert result.session_id is not None
    assert result.session_id >= 1


async def test_pipeline_extracts_approved_decision(db_with_schema, tmp_path):
    with patch("src.agents.base.invoke_claude_with_retry", new_callable=AsyncMock) as mock:
        mock.side_effect = [PLAN_OUTPUT, EXECUTE_OUTPUT, REVIEW_OUTPUT]
        result = await run_pipeline("Build an API", str(tmp_path), db_with_schema)

    assert result.final_decision == "APPROVED"


async def test_pipeline_extracts_back_to_plan_decision(db_with_schema, tmp_path):
    review_back = REVIEW_OUTPUT.replace("APPROVED", "BACK TO PLAN")
    with patch("src.agents.base.invoke_claude_with_retry", new_callable=AsyncMock) as mock:
        mock.side_effect = [PLAN_OUTPUT, EXECUTE_OUTPUT, review_back]
        result = await run_pipeline("Build an API", str(tmp_path), db_with_schema)

    assert result.final_decision == "BACK TO PLAN"


async def test_pipeline_passes_handoff_context(db_with_schema, tmp_path):
    prompts_received = []

    async def capture_prompt(prompt, **kwargs):
        prompts_received.append(prompt)
        if len(prompts_received) == 1:
            return PLAN_OUTPUT
        elif len(prompts_received) == 2:
            return EXECUTE_OUTPUT
        return REVIEW_OUTPUT

    with patch("src.agents.base.invoke_claude_with_retry", new_callable=AsyncMock) as mock:
        mock.side_effect = capture_prompt
        await run_pipeline("Build an API", str(tmp_path), db_with_schema)

    # Second prompt (execute) should contain handoff from plan
    assert "HANDOFF FROM PLAN" in prompts_received[1]
    # Third prompt (review) should contain handoff from execute
    assert "HANDOFF FROM EXECUTE" in prompts_received[2]


async def test_pipeline_steps_match_pipeline_order(db_with_schema, tmp_path):
    with patch("src.agents.base.invoke_claude_with_retry", new_callable=AsyncMock) as mock:
        mock.side_effect = [PLAN_OUTPUT, EXECUTE_OUTPUT, REVIEW_OUTPUT]
        result = await run_pipeline("Build an API", str(tmp_path), db_with_schema)

    step_names = [s.agent_name for s in result.steps]
    assert step_names == PIPELINE_STEPS
