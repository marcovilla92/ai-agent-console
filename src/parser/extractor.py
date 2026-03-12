"""
Structured section extractor for Claude agent output.

Handles:
- Uppercase headers:   GOAL:
- Title-case headers:  Goal:
- Bold markdown:       **Goal:**
- Mixed:               **GOAL:**

Falls back to {"CONTENT": text} when no sections found.
"""
import re

# Matches optional bold markers, then a header word, then optional bold, then colon at line end.
# Handles: GOAL:, Goal:, **Goal:**, **GOAL:**, Tasks:
SECTION_RE = re.compile(
    r'^\*{0,2}([A-Za-z][A-Za-z ]{0,30}?)\*{0,2}:\*{0,2}\s*$',
    re.MULTILINE | re.IGNORECASE,
)


def extract_sections(text: str) -> dict[str, str]:
    """
    Parse structured sections from Claude agent output text.

    Returns dict mapping UPPERCASE section name -> content string.
    Falls back to {"CONTENT": text.strip()} when no sections are found.

    Examples:
        "GOAL:\\nBuild it\\n\\nTASKS:\\n1. Do it"
        -> {"GOAL": "Build it", "TASKS": "1. Do it"}

        "Just plain text without headers"
        -> {"CONTENT": "Just plain text without headers"}
    """
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return {"CONTENT": text.strip()}

    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        header = match.group(1).strip().upper()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[header] = text[start:end].strip()
    return sections
