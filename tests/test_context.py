from src.context.assembler import assemble_workspace_context


def test_context_includes_project_path(tmp_path):
    """INFR-09: context output contains the project path."""
    ctx = assemble_workspace_context(str(tmp_path))
    assert f"Project path: {tmp_path}" in ctx


def test_context_detects_stack(tmp_path):
    """INFR-09: pyproject.toml present -> 'Python' in detected stack."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")
    ctx = assemble_workspace_context(str(tmp_path))
    assert "Python" in ctx


def test_context_excludes_ignored_dirs(tmp_path):
    """INFR-09: .git directory files excluded from file list."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("# main")

    ctx = assemble_workspace_context(str(tmp_path))
    assert ".git" not in ctx.split("Files")[1]  # .git should not appear in file list


def test_context_caps_at_200_files(tmp_path):
    """INFR-09: file listing capped at 200 entries even with 250 files."""
    src = tmp_path / "src"
    src.mkdir()
    for i in range(250):
        (src / f"file_{i:04d}.py").write_text("# stub")

    ctx = assemble_workspace_context(str(tmp_path))
    # Count lines starting with "  - "
    file_lines = [line for line in ctx.splitlines() if line.startswith("  - ")]
    assert len(file_lines) == 200
