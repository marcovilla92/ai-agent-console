import pytest


@pytest.mark.skip(reason="stub -- implement in plan 02")
def test_extract_sections_well_formed():
    """INFR-01 parsing: GOAL/TASKS sections extracted from well-formed text."""
    pass


@pytest.mark.skip(reason="stub -- implement in plan 02")
def test_extract_sections_fallback():
    """INFR-01 parsing: unstructured text returns {'CONTENT': text}."""
    pass


@pytest.mark.skip(reason="stub -- implement in plan 02")
def test_extract_sections_bold_markdown_headers():
    """INFR-01 parsing: **Goal:** bold markdown headers are normalized and matched."""
    pass
