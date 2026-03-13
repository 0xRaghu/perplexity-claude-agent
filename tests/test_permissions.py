"""Tests for permissions module."""

import pytest

from perplexity_claude_agent.permissions import (
    DEFAULT_PERMISSION,
    PERMISSION_PRESETS,
    get_permission_mode,
    list_presets,
)


class TestGetPermissionMode:
    """Tests for get_permission_mode function."""

    def test_get_permission_mode_default(self):
        """Test that 'default' preset returns 'default' mode."""
        assert get_permission_mode("default") == "default"

    def test_get_permission_mode_safe(self):
        """Test that 'safe' preset returns 'acceptEdits' mode."""
        assert get_permission_mode("safe") == "acceptEdits"

    def test_get_permission_mode_plan(self):
        """Test that 'plan' preset returns 'plan' mode."""
        assert get_permission_mode("plan") == "plan"

    def test_get_permission_mode_full(self):
        """Test that 'full' preset returns 'bypassPermissions' mode."""
        assert get_permission_mode("full") == "bypassPermissions"

    def test_get_permission_mode_invalid(self):
        """Test that unknown preset raises ValueError."""
        with pytest.raises(ValueError, match="Unknown permission preset"):
            get_permission_mode("invalid")


class TestListPresets:
    """Tests for list_presets function."""

    def test_list_presets_returns_all(self):
        """Test that list_presets returns all presets."""
        presets = list_presets()

        # Should have 4 presets: default, safe, plan, full
        assert len(presets) == 4

        preset_names = [p[0] for p in presets]
        assert "default" in preset_names
        assert "safe" in preset_names
        assert "plan" in preset_names
        assert "full" in preset_names

    def test_list_presets_has_descriptions(self):
        """Test that each preset has a description."""
        presets = list_presets()

        for name, description in presets:
            assert isinstance(description, str)
            assert len(description) > 0


class TestDefaultPermission:
    """Tests for DEFAULT_PERMISSION constant."""

    def test_default_permission_is_safe(self):
        """Test that DEFAULT_PERMISSION is 'safe'."""
        assert DEFAULT_PERMISSION == "safe"

    def test_default_permission_is_valid(self):
        """Test that DEFAULT_PERMISSION is a valid preset."""
        assert DEFAULT_PERMISSION in PERMISSION_PRESETS
