from src.parser.extractor import extract_sections


def test_extract_sections_well_formed():
    """INFR-01 parsing: GOAL/TASKS sections extracted from well-formed uppercase text."""
    text = "GOAL:\nBuild something\n\nTASKS:\n1. Do it"
    result = extract_sections(text)
    assert result == {"GOAL": "Build something", "TASKS": "1. Do it"}


def test_extract_sections_fallback():
    """INFR-01 parsing: unstructured text returns {'CONTENT': text}."""
    text = "Just a plain response with no headers at all."
    result = extract_sections(text)
    assert result == {"CONTENT": text.strip()}


def test_extract_sections_bold_markdown_headers():
    """INFR-01 parsing: **Goal:** markdown bold stripped and matched."""
    text = "**Goal:**\nBuild it\n\n**Tasks:**\n1. Step one"
    result = extract_sections(text)
    assert "GOAL" in result
    assert result["GOAL"] == "Build it"
    assert "TASKS" in result
    assert result["TASKS"] == "1. Step one"


def test_extract_sections_mixed_case():
    """INFR-01 parsing: Title-case headers matched case-insensitively."""
    text = "Tasks:\nDo this first\n\nNotes:\nRemember this"
    result = extract_sections(text)
    assert "TASKS" in result
    assert result["TASKS"] == "Do this first"
    assert "NOTES" in result
