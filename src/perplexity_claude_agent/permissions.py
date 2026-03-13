"""Permission hooks for controlling Claude Code's tool access.

This module implements granular permission control for what tools and
operations Perplexity Computer can execute via Claude Code, ensuring
security boundaries are maintained.
"""

from __future__ import annotations

from typing import TypedDict


class PermissionPreset(TypedDict):
    """Definition of a permission preset."""

    description: str
    permission_mode: str


PERMISSION_PRESETS: dict[str, PermissionPreset] = {
    "default": {
        "description": "Standard permissions — Claude asks before destructive operations",
        "permission_mode": "default",
    },
    "safe": {
        "description": "Auto-accept file edits, prompt for commands — recommended for tunnels",
        "permission_mode": "acceptEdits",
    },
    "plan": {
        "description": "Plan-only mode — Claude proposes changes but doesn't execute",
        "permission_mode": "plan",
    },
    "full": {
        "description": "Full access — skip all permission prompts (use with caution)",
        "permission_mode": "bypassPermissions",
    },
}

DEFAULT_PERMISSION = "safe"


def get_permission_mode(preset: str = DEFAULT_PERMISSION) -> str:
    """Get the SDK permission_mode for a preset name.

    Args:
        preset: The preset name ("default", "plan", or "full").

    Returns:
        The corresponding permission_mode string for the SDK.

    Raises:
        ValueError: If the preset name is not recognized.
    """
    if preset not in PERMISSION_PRESETS:
        raise ValueError(
            f"Unknown permission preset: {preset}. "
            f"Options: {list(PERMISSION_PRESETS.keys())}"
        )
    return PERMISSION_PRESETS[preset]["permission_mode"]


def list_presets() -> list[tuple[str, str]]:
    """List all available permission presets.

    Returns:
        List of (name, description) tuples.
    """
    return [(name, info["description"]) for name, info in PERMISSION_PRESETS.items()]
