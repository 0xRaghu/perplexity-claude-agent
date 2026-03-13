"""Project registry for managing local project directories.

This module handles registration and management of local projects that
Perplexity Computer can access via Claude Code. Configuration is stored
at ~/.perplexity-claude-agent/config.json.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    """A registered local project."""

    name: str
    """Unique slug, e.g. 'my-saas'."""

    path: str
    """Absolute path, e.g. '/Users/raghu/Projects/pilan'."""

    description: str = ""
    """Auto-detected or user-provided description."""

    tech_stack: list[str] = Field(default_factory=list)
    """Auto-detected tech stack, e.g. ['python', 'react']."""

    created_at: datetime
    """When the project was registered."""

    last_accessed: datetime | None = None
    """Last time a session was opened for this project."""


class RegistryConfig(BaseModel):
    """Top-level config file."""

    projects: dict[str, ProjectConfig] = Field(default_factory=dict)
    """Registered projects keyed by project name."""

    default_project: str | None = None
    """Optional default project name."""

    config_version: str = "1.0"
    """Config file version for future migrations."""


def slugify(name: str) -> str:
    """Convert a directory name to a clean slug.

    Converts to lowercase, replaces spaces/underscores with hyphens,
    and strips special characters.

    Args:
        name: The string to slugify.

    Returns:
        A clean, URL-safe slug.
    """
    # Convert to lowercase
    slug = name.lower()
    # Replace spaces and underscores with hyphens
    slug = re.sub(r"[\s_]+", "-", slug)
    # Remove any character that isn't alphanumeric or hyphen
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    # Remove consecutive hyphens
    slug = re.sub(r"-+", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    return slug


class ProjectRegistry:
    """Manages local project registration and configuration."""

    DEFAULT_CONFIG_DIR = Path.home() / ".perplexity-claude-agent"
    CONFIG_FILENAME = "config.json"

    def __init__(self, config_dir: Path | None = None) -> None:
        """Initialize the project registry.

        Args:
            config_dir: Directory for config storage. Defaults to
                ~/.perplexity-claude-agent/
        """
        self.config_dir = config_dir or self.DEFAULT_CONFIG_DIR
        self.config_path = self.config_dir / self.CONFIG_FILENAME

        # Create config directory if it doesn't exist
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(
                f"Failed to create config directory {self.config_dir}: {e}"
            ) from e

        # Load existing config or create new one
        self._config = self._load_config()

    def _load_config(self) -> RegistryConfig:
        """Read and parse config.json.

        Returns:
            The loaded RegistryConfig, or a new empty one if file doesn't exist.
        """
        if not self.config_path.exists():
            return RegistryConfig()

        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return RegistryConfig.model_validate(data)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Invalid JSON in config file {self.config_path}: {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Failed to load config from {self.config_path}: {e}"
            ) from e

    def _save_config(self) -> None:
        """Atomically write config to disk.

        Writes to a temporary file first, then renames for atomicity.
        """
        tmp_path = self.config_path.with_suffix(".tmp")

        try:
            # Serialize with nice formatting
            data = self._config.model_dump(mode="json")
            json_str = json.dumps(data, indent=2, default=str)

            # Write to temp file
            with tmp_path.open("w", encoding="utf-8") as f:
                f.write(json_str)
                f.write("\n")  # Trailing newline

            # Atomic rename
            tmp_path.rename(self.config_path)
        except Exception as e:
            # Clean up temp file if it exists
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise RuntimeError(f"Failed to save config to {self.config_path}: {e}") from e

    def _detect_description(self, project_path: Path) -> str:
        """Auto-detect project description from CLAUDE.md or README.md.

        Args:
            project_path: Path to the project directory.

        Returns:
            The detected description, or empty string if not found.
        """
        # Try CLAUDE.md first - look for first non-header, non-empty line
        claude_md = project_path / "CLAUDE.md"
        if claude_md.exists():
            try:
                content = claude_md.read_text(encoding="utf-8")
                for line in content.split("\n"):
                    line = line.strip()
                    # Skip empty lines and headers
                    if line and not line.startswith("#"):
                        return line[:200]  # Limit length
            except OSError:
                pass

        # Try README.md - get first paragraph
        readme_md = project_path / "README.md"
        if readme_md.exists():
            try:
                content = readme_md.read_text(encoding="utf-8")
                in_paragraph = False
                paragraph_lines: list[str] = []

                for line in content.split("\n"):
                    stripped = line.strip()

                    # Skip headers and empty lines at start
                    if not in_paragraph:
                        if stripped and not stripped.startswith("#"):
                            in_paragraph = True
                            paragraph_lines.append(stripped)
                    else:
                        # End paragraph on empty line or header
                        if not stripped or stripped.startswith("#"):
                            break
                        paragraph_lines.append(stripped)

                if paragraph_lines:
                    return " ".join(paragraph_lines)[:200]
            except OSError:
                pass

        return ""

    def _detect_tech_stack(self, project_path: Path) -> list[str]:
        """Auto-detect the project's tech stack from config files.

        Args:
            project_path: Path to the project directory.

        Returns:
            List of detected technologies.
        """
        tech_stack: list[str] = []

        # Check for package.json (JavaScript/TypeScript)
        package_json = project_path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
                deps: dict[str, Any] = {}
                deps.update(data.get("dependencies", {}))
                deps.update(data.get("devDependencies", {}))

                # Check for TypeScript
                if "typescript" in deps or (project_path / "tsconfig.json").exists():
                    tech_stack.append("typescript")
                else:
                    tech_stack.append("javascript")

                # Check for common frameworks
                if "react" in deps:
                    tech_stack.append("react")
                if "next" in deps:
                    tech_stack.append("nextjs")
                if "vue" in deps:
                    tech_stack.append("vue")
                if "svelte" in deps:
                    tech_stack.append("svelte")
                if "express" in deps:
                    tech_stack.append("express")
            except (json.JSONDecodeError, OSError):
                tech_stack.append("javascript")

        # Check for Python
        if (project_path / "pyproject.toml").exists():
            tech_stack.append("python")
        elif (project_path / "requirements.txt").exists():
            tech_stack.append("python")
        elif (project_path / "setup.py").exists():
            tech_stack.append("python")

        # Check for Rust
        if (project_path / "Cargo.toml").exists():
            tech_stack.append("rust")

        # Check for Go
        if (project_path / "go.mod").exists():
            tech_stack.append("go")

        # Check for Ruby
        if (project_path / "Gemfile").exists():
            tech_stack.append("ruby")

        # Check for Swift
        if (project_path / "Package.swift").exists():
            tech_stack.append("swift")
        elif any(project_path.glob("*.xcodeproj")):
            tech_stack.append("swift")

        # Check for Java/Kotlin
        if (project_path / "pom.xml").exists():
            tech_stack.append("java")
        elif (project_path / "build.gradle").exists() or (
            project_path / "build.gradle.kts"
        ).exists():
            if any(project_path.rglob("*.kt")):
                tech_stack.append("kotlin")
            else:
                tech_stack.append("java")

        return tech_stack

    def add_project(
        self,
        path: str,
        name: str | None = None,
        description: str | None = None,
    ) -> ProjectConfig:
        """Register a new project.

        Args:
            path: Path to the project directory.
            name: Optional project name. If not provided, uses directory basename.
            description: Optional description. If not provided, auto-detects.

        Returns:
            The created ProjectConfig.

        Raises:
            ValueError: If project name already exists or path is invalid.
        """
        # Resolve to absolute path
        project_path = Path(path).expanduser().resolve()

        # Validate directory exists
        if not project_path.exists():
            raise ValueError(f"Path does not exist: {project_path}")
        if not project_path.is_dir():
            raise ValueError(f"Path is not a directory: {project_path}")

        # Generate name if not provided
        if name is None:
            name = slugify(project_path.name)

        if not name:
            raise ValueError("Project name cannot be empty")

        # Check for duplicate
        if name in self._config.projects:
            raise ValueError(f"Project '{name}' already exists")

        # Auto-detect description if not provided
        if description is None:
            description = self._detect_description(project_path)

        # Auto-detect tech stack
        tech_stack = self._detect_tech_stack(project_path)

        # Create project config
        project = ProjectConfig(
            name=name,
            path=str(project_path),
            description=description,
            tech_stack=tech_stack,
            created_at=datetime.now(timezone.utc),
            last_accessed=None,
        )

        # Save to config
        self._config.projects[name] = project
        self._save_config()

        return project

    def remove_project(self, name: str) -> bool:
        """Remove a project by name.

        Args:
            name: The project name to remove.

        Returns:
            True if the project was found and removed, False otherwise.
        """
        if name not in self._config.projects:
            return False

        del self._config.projects[name]

        # Clear default if it was this project
        if self._config.default_project == name:
            self._config.default_project = None

        self._save_config()
        return True

    def get_project(self, name: str) -> ProjectConfig | None:
        """Get a project by name.

        Args:
            name: The project name to look up.

        Returns:
            The ProjectConfig if found, None otherwise.
        """
        return self._config.projects.get(name)

    def list_projects(self) -> list[ProjectConfig]:
        """List all registered projects.

        Returns:
            List of all ProjectConfig objects.
        """
        return list(self._config.projects.values())

    def set_default(self, name: str) -> None:
        """Set the default project.

        Args:
            name: The project name to set as default.

        Raises:
            ValueError: If the project doesn't exist.
        """
        if name not in self._config.projects:
            raise ValueError(f"Project '{name}' does not exist")

        self._config.default_project = name
        self._save_config()

    def get_default(self) -> ProjectConfig | None:
        """Get the default project.

        Returns:
            The default ProjectConfig if set, None otherwise.
        """
        if self._config.default_project is None:
            return None
        return self._config.projects.get(self._config.default_project)

    def update_last_accessed(self, name: str) -> None:
        """Update the last_accessed timestamp for a project.

        Args:
            name: The project name to update.

        Raises:
            ValueError: If the project doesn't exist.
        """
        if name not in self._config.projects:
            raise ValueError(f"Project '{name}' does not exist")

        self._config.projects[name].last_accessed = datetime.now(timezone.utc)
        self._save_config()
