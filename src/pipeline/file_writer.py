"""
File writer module.

Parses the EXECUTE agent's CODE section to extract code blocks with
file path annotations, writes them to disk under the project workspace,
and reports which files were written.

Supports multiple annotation formats:
1. ```lang # path/to/file  (primary)
2. ```lang\n# path/to/file  (comment fallback)
3. ## path/to/file\n```lang  (header fallback)
"""
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

# Pattern 1: ```lang # path/to/file
CODE_BLOCK_RE = re.compile(
    r'```(\w+)\s+#\s+(.+?)\s*\n(.*?)```',
    re.DOTALL,
)

# Pattern 2: ```lang\n// path or # path (first line comment)
CODE_BLOCK_COMMENT_RE = re.compile(
    r'```(\w+)\s*\n(?://|#)\s*(.+?)\s*\n(.*?)```',
    re.DOTALL,
)

# Pattern 3: ## path/to/file\n```lang
CODE_BLOCK_HEADER_RE = re.compile(
    r'##\s+(.+?)\s*\n```(\w+)\s*\n(.*?)```',
    re.DOTALL,
)


def parse_code_blocks(code_section: str) -> list[tuple[str, str, str]]:
    """Parse code blocks from CODE section.

    Returns list of (relative_path, language, content) tuples.
    Deduplicates by normalized path; first match wins.
    """
    results: list[tuple[str, str, str]] = []
    seen_paths: set[str] = set()

    # Patterns where group order is (lang, path, content)
    for pattern in [CODE_BLOCK_RE, CODE_BLOCK_COMMENT_RE]:
        for match in pattern.finditer(code_section):
            lang = match.group(1)
            path = match.group(2).strip()
            content = match.group(3)
            normalized = path.lstrip("./")
            if normalized not in seen_paths:
                seen_paths.add(normalized)
                results.append((normalized, lang, content.rstrip()))

    # Pattern 3 has reversed group order (path first, then lang)
    for match in CODE_BLOCK_HEADER_RE.finditer(code_section):
        path = match.group(1).strip()
        lang = match.group(2)
        content = match.group(3)
        normalized = path.lstrip("./")
        if normalized not in seen_paths:
            seen_paths.add(normalized)
            results.append((normalized, lang, content.rstrip()))

    return results


def write_files(
    workspace: str, blocks: list[tuple[str, str, str]]
) -> list[str]:
    """Write parsed code blocks to disk under workspace.

    Creates directories as needed. Overwrites existing files.

    Returns list of absolute paths of written files.
    """
    written: list[str] = []
    workspace_path = Path(workspace)

    for rel_path, _lang, content in blocks:
        target = workspace_path / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content + "\n", encoding="utf-8")
        written.append(str(target))
        log.info("file_writer: wrote %s (%d chars)", target, len(content))

    return written


def process_execute_output(
    workspace: str, sections: dict[str, str]
) -> list[str]:
    """Process execute agent output: parse CODE section and write files.

    Returns list of absolute paths of written files.
    Logs warning if CODE section is non-empty but zero files extracted.
    """
    code_section = sections.get("CODE", "")
    if not code_section.strip():
        log.info("file_writer: no CODE section or empty, skipping")
        return []

    blocks = parse_code_blocks(code_section)

    if not blocks:
        log.warning(
            "file_writer: CODE section non-empty (%d chars) but zero files extracted",
            len(code_section),
        )
        return []

    written = write_files(workspace, blocks)
    log.info("file_writer: processed %d files from CODE section", len(written))
    return written
