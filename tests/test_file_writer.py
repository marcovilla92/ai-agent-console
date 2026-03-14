"""Tests for src/pipeline/file_writer.py — FWRT-01 through FWRT-05."""
import logging
import os

import pytest

from src.pipeline.file_writer import parse_code_blocks, process_execute_output, write_files


class TestParseCodeBlocks:
    """FWRT-01: Parse code blocks with file path annotations."""

    def test_parse_primary_format(self):
        code = '```python # src/main.py\ndef main():\n    pass\n```'
        result = parse_code_blocks(code)
        assert len(result) == 1
        assert result[0][0] == "src/main.py"
        assert result[0][1] == "python"
        assert "def main():" in result[0][2]

    def test_parse_multiple_blocks(self):
        code = (
            '```python # src/a.py\nprint("a")\n```\n\n'
            '```javascript # src/b.js\nconsole.log("b")\n```'
        )
        result = parse_code_blocks(code)
        assert len(result) == 2
        assert result[0][0] == "src/a.py"
        assert result[1][0] == "src/b.js"

    def test_parse_comment_fallback(self):
        code = '```python\n# src/fallback.py\nprint("hi")\n```'
        result = parse_code_blocks(code)
        assert len(result) == 1
        assert result[0][0] == "src/fallback.py"

    def test_parse_header_fallback(self):
        code = '## src/header.py\n```python\nprint("hi")\n```'
        result = parse_code_blocks(code)
        assert len(result) == 1
        assert result[0][0] == "src/header.py"

    def test_no_duplicates(self):
        code = '```python # src/dup.py\nv1\n```\n```python # src/dup.py\nv2\n```'
        result = parse_code_blocks(code)
        assert len(result) == 1

    def test_strips_leading_dot_slash(self):
        code = '```python # ./src/main.py\npass\n```'
        result = parse_code_blocks(code)
        assert result[0][0] == "src/main.py"

    def test_empty_input(self):
        assert parse_code_blocks("") == []
        assert parse_code_blocks("no code blocks here") == []


class TestWriteFiles:
    """FWRT-02, FWRT-03: Write files and create directories."""

    def test_write_single_file(self, tmp_path):
        blocks = [("src/main.py", "python", "print('hello')")]
        written = write_files(str(tmp_path), blocks)
        assert len(written) == 1
        assert (tmp_path / "src" / "main.py").read_text().strip() == "print('hello')"

    def test_creates_nested_directories(self, tmp_path):
        blocks = [("a/b/c/deep.py", "python", "pass")]
        write_files(str(tmp_path), blocks)
        assert (tmp_path / "a" / "b" / "c" / "deep.py").exists()

    def test_overwrites_existing_file(self, tmp_path):
        (tmp_path / "file.py").write_text("old")
        blocks = [("file.py", "python", "new")]
        write_files(str(tmp_path), blocks)
        assert (tmp_path / "file.py").read_text().strip() == "new"

    def test_returns_absolute_paths(self, tmp_path):
        blocks = [("src/x.py", "python", "pass")]
        written = write_files(str(tmp_path), blocks)
        assert os.path.isabs(written[0])


class TestProcessExecuteOutput:
    """FWRT-04, FWRT-05: Main entry point with reporting and zero-file warning."""

    def test_returns_written_file_list(self, tmp_path):
        sections = {"CODE": '```python # src/app.py\nprint("ok")\n```'}
        result = process_execute_output(str(tmp_path), sections)
        assert len(result) == 1
        assert "app.py" in result[0]

    def test_empty_code_section_returns_empty(self, tmp_path):
        sections = {"CODE": ""}
        assert process_execute_output(str(tmp_path), sections) == []

    def test_no_code_section_returns_empty(self, tmp_path):
        sections = {"TARGET": "something"}
        assert process_execute_output(str(tmp_path), sections) == []

    def test_zero_file_extraction_warning(self, tmp_path, caplog):
        sections = {"CODE": "This has content but no valid code blocks"}
        with caplog.at_level(logging.WARNING):
            result = process_execute_output(str(tmp_path), sections)
        assert result == []
        assert "zero files extracted" in caplog.text

    def test_multiple_files_all_written(self, tmp_path):
        sections = {
            "CODE": (
                '```python # src/a.py\nprint("a")\n```\n\n'
                '```python # src/b.py\nprint("b")\n```'
            )
        }
        result = process_execute_output(str(tmp_path), sections)
        assert len(result) == 2
        assert (tmp_path / "src" / "a.py").exists()
        assert (tmp_path / "src" / "b.py").exists()
