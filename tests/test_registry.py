"""Tests for project registry."""

import pytest
from pathlib import Path

from perplexity_claude_agent.registry import ProjectRegistry, slugify


class TestSlugify:
    """Tests for the slugify helper function."""

    def test_slugify_lowercase(self):
        """Verify slugify converts to lowercase."""
        assert slugify("MyProject") == "myproject"

    def test_slugify_spaces_to_hyphens(self):
        """Verify slugify converts spaces to hyphens."""
        assert slugify("My Cool Project") == "my-cool-project"

    def test_slugify_underscores_to_hyphens(self):
        """Verify slugify converts underscores to hyphens."""
        assert slugify("my_cool_project") == "my-cool-project"

    def test_slugify_removes_special_chars(self):
        """Verify slugify removes special characters."""
        assert slugify("my@project!") == "myproject"

    def test_slugify_strips_hyphens(self):
        """Verify slugify strips leading/trailing hyphens."""
        assert slugify("-my-project-") == "my-project"

    def test_slugify_consecutive_hyphens(self):
        """Verify slugify collapses consecutive hyphens."""
        assert slugify("my---project") == "my-project"


class TestProjectRegistry:
    """Tests for the ProjectRegistry class."""

    def test_add_project(self, registry: ProjectRegistry, sample_project: Path):
        """Test adding a project to the registry."""
        project = registry.add_project(str(sample_project))

        assert project.name == "my-project"
        assert project.path == str(sample_project)

        # Verify it appears in list
        projects = registry.list_projects()
        assert len(projects) == 1
        assert projects[0].name == "my-project"

    def test_add_project_auto_detect_python(
        self, registry: ProjectRegistry, sample_project: Path
    ):
        """Test that pyproject.toml triggers Python detection."""
        project = registry.add_project(str(sample_project))

        assert "python" in project.tech_stack

    def test_add_project_auto_detect_js(
        self, registry: ProjectRegistry, sample_js_project: Path
    ):
        """Test that package.json triggers JavaScript/React detection."""
        project = registry.add_project(str(sample_js_project))

        assert "javascript" in project.tech_stack
        assert "react" in project.tech_stack

    def test_add_project_auto_detect_description(
        self, registry: ProjectRegistry, sample_project: Path
    ):
        """Test that description is auto-detected from README."""
        project = registry.add_project(str(sample_project))

        assert "test project" in project.description.lower()

    def test_add_project_custom_name(
        self, registry: ProjectRegistry, sample_project: Path
    ):
        """Test adding a project with a custom name."""
        project = registry.add_project(str(sample_project), name="custom-name")

        assert project.name == "custom-name"

    def test_add_project_duplicate_raises(
        self, registry: ProjectRegistry, sample_project: Path
    ):
        """Test that adding a duplicate project raises ValueError."""
        registry.add_project(str(sample_project))

        with pytest.raises(ValueError, match="already exists"):
            registry.add_project(str(sample_project))

    def test_remove_project(self, registry: ProjectRegistry, sample_project: Path):
        """Test removing a project from the registry."""
        registry.add_project(str(sample_project))
        assert len(registry.list_projects()) == 1

        removed = registry.remove_project("my-project")

        assert removed is True
        assert len(registry.list_projects()) == 0

    def test_remove_nonexistent_project(self, registry: ProjectRegistry):
        """Test that removing a nonexistent project returns False."""
        removed = registry.remove_project("nonexistent")

        assert removed is False

    def test_get_project_not_found(self, registry: ProjectRegistry):
        """Test that get_project returns None for unknown projects."""
        project = registry.get_project("nonexistent")

        assert project is None

    def test_get_project_found(
        self, registry: ProjectRegistry, sample_project: Path
    ):
        """Test that get_project returns the project when found."""
        registry.add_project(str(sample_project))

        project = registry.get_project("my-project")

        assert project is not None
        assert project.name == "my-project"

    def test_set_default(self, registry: ProjectRegistry, sample_project: Path):
        """Test setting a default project."""
        registry.add_project(str(sample_project))
        registry.set_default("my-project")

        default = registry.get_default()

        assert default is not None
        assert default.name == "my-project"

    def test_set_default_nonexistent_raises(self, registry: ProjectRegistry):
        """Test that setting a nonexistent project as default raises."""
        with pytest.raises(ValueError, match="does not exist"):
            registry.set_default("nonexistent")

    def test_update_last_accessed(
        self, registry: ProjectRegistry, sample_project: Path
    ):
        """Test updating last_accessed timestamp."""
        project = registry.add_project(str(sample_project))
        original_accessed = project.last_accessed

        registry.update_last_accessed("my-project")

        updated = registry.get_project("my-project")
        assert updated is not None
        assert updated.last_accessed is not None
        assert updated.last_accessed != original_accessed
