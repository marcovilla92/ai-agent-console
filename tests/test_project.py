"""Tests for project creation."""
import pytest
from pathlib import Path

from src.pipeline.project import create_project, sanitize_project_name


def test_sanitize_simple_name():
    assert sanitize_project_name("My Project") == "my-project"


def test_sanitize_special_chars():
    assert sanitize_project_name("Hello, World!") == "hello-world"


def test_sanitize_already_clean():
    assert sanitize_project_name("my-app") == "my-app"


def test_sanitize_empty_raises():
    with pytest.raises(ValueError, match="empty directory name"):
        sanitize_project_name("!!!")


def test_create_project_makes_directory(tmp_path):
    path = create_project("Test App", str(tmp_path))
    assert Path(path).is_dir()
    assert Path(path).name == "test-app"


def test_create_project_has_src_dir(tmp_path):
    path = create_project("Test App", str(tmp_path))
    assert (Path(path) / "src").is_dir()


def test_create_project_duplicate_raises(tmp_path):
    create_project("Test App", str(tmp_path))
    with pytest.raises(FileExistsError):
        create_project("Test App", str(tmp_path))
