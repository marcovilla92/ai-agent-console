"""Tests for the Alpine.js SPA (static/index.html).

These tests validate the SPA HTML file directly by reading from disk.
No server requests are made -- server integration tests are in plan 02.
"""

import pathlib

import pytest

SPA_PATH = pathlib.Path(__file__).resolve().parent.parent / "static" / "index.html"


@pytest.fixture
def spa_html():
    """Read the SPA HTML file from disk."""
    return SPA_PATH.read_text()


def test_html_contains_alpine_store(spa_html):
    """HTML contains Alpine.store (proves it's the SPA, not Jinja2)."""
    assert "Alpine.store" in spa_html


def test_html_contains_project_list(spa_html):
    """HTML contains project list view with loadProjects."""
    assert "x-show=\"$store.app.view === 'select'\"" in spa_html
    assert "loadProjects" in spa_html


def test_html_contains_create_form(spa_html):
    """HTML contains create project view with template picker."""
    assert "x-show=\"$store.app.view === 'create'\"" in spa_html
    assert "template" in spa_html.lower()


def test_html_contains_prompt_view(spa_html):
    """HTML contains prompt view with phase suggestion."""
    assert "x-show=\"$store.app.view === 'prompt'\"" in spa_html
    assert "phaseSuggestion" in spa_html


def test_html_contains_ws_streaming(spa_html):
    """HTML contains WebSocket streaming with connectWS."""
    assert "WebSocket" in spa_html
    assert "connectWS" in spa_html
    assert "logText" in spa_html


def test_uses_xshow_not_xif_for_views(spa_html):
    """Views use x-show (not x-if) to preserve DOM and WS connections."""
    # Must have x-show for all 4 views
    assert "x-show=\"$store.app.view === 'select'\"" in spa_html
    assert "x-show=\"$store.app.view === 'create'\"" in spa_html
    assert "x-show=\"$store.app.view === 'prompt'\"" in spa_html
    assert "x-show=\"$store.app.view === 'running'\"" in spa_html
    # Must NOT use x-if for view switching (would destroy DOM/WS)
    assert "x-if=\"$store.app.view" not in spa_html


def test_html_includes_cdn_libs(spa_html):
    """HTML includes Pico CSS and Alpine.js CDN links."""
    assert "picocss/pico@2" in spa_html or "pico@2" in spa_html
    assert "alpinejs@3" in spa_html


def test_html_has_all_api_endpoints(spa_html):
    """HTML contains fetch calls to all required API endpoints with credentials."""
    # Check API endpoint patterns
    assert "fetch('/projects'" in spa_html or 'fetch("/projects"' in spa_html or "fetch(`/projects`" in spa_html
    assert "fetch('/templates'" in spa_html or 'fetch("/templates"' in spa_html or "fetch(`/templates`" in spa_html
    assert "fetch('/tasks'" in spa_html or 'fetch("/tasks"' in spa_html or "fetch(`/tasks`" in spa_html
    # All fetches must use credentials
    assert "credentials: 'same-origin'" in spa_html
