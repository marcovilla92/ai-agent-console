"""Tests for targeted re-route prompt building (CTX-07)."""
from src.pipeline.handoff import build_reroute_prompt


class TestBuildReroutePrompt:
    def test_targeted_includes_issues(self):
        sections = {
            "ISSUES": "1. Missing error handling\n2. No input validation",
            "IMPROVEMENTS": "Add logging",
            "DECISION": "BACK TO EXECUTE -- needs fixes",
        }
        result = build_reroute_prompt(sections, "Build a REST API")
        assert "Missing error handling" in result
        assert "No input validation" in result
        assert "Build a REST API" in result

    def test_targeted_excludes_no_issues(self):
        sections = {
            "ISSUES": "No issues found.",
            "IMPROVEMENTS": "Could add tests",
            "DECISION": "BACK TO EXECUTE",
        }
        result = build_reroute_prompt(sections, "prompt")
        assert "ISSUES TO FIX" not in result
        assert "Could add tests" in result

    def test_targeted_includes_decision(self):
        sections = {"DECISION": "BACK TO EXECUTE -- critical bugs"}
        result = build_reroute_prompt(sections, "prompt")
        assert "critical bugs" in result

    def test_targeted_preserves_original_prompt(self):
        sections = {"ISSUES": "Bug found"}
        result = build_reroute_prompt(sections, "Build a CLI tool")
        assert "Build a CLI tool" in result

    def test_targeted_handles_empty_sections(self):
        result = build_reroute_prompt({}, "prompt")
        assert "RE-ROUTE" in result
        assert "prompt" in result
