"""Shared fixtures for tests."""

import pytest
from pathlib import Path

from perplexity_claude_agent.registry import ProjectRegistry


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    """Provide a temporary config directory."""
    config_dir = tmp_path / "config"
    return config_dir


@pytest.fixture
def registry(tmp_config: Path) -> ProjectRegistry:
    """Provide a ProjectRegistry with a temp config directory."""
    return ProjectRegistry(config_dir=tmp_config)


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Create a sample project directory with typical files."""
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()
    # Add pyproject.toml
    (project_dir / "pyproject.toml").write_text('[project]\nname = "test"\n')
    # Add README
    (project_dir / "README.md").write_text("# Test Project\n\nA test project for testing.\n")
    return project_dir


@pytest.fixture
def sample_js_project(tmp_path: Path) -> Path:
    """Create a sample JavaScript project directory."""
    project_dir = tmp_path / "js-app"
    project_dir.mkdir()
    # Add package.json with React
    (project_dir / "package.json").write_text(
        '{"name": "js-app", "dependencies": {"react": "18.0.0"}}'
    )
    return project_dir
