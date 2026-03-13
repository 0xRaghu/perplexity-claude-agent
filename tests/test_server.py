"""Tests for the MCP server."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from perplexity_claude_agent.registry import ProjectRegistry
from perplexity_claude_agent.server import (
    BearerAuthMiddleware,
    create_server,
)
from perplexity_claude_agent.session import SessionManager


@pytest.fixture
def registry_with_projects(tmp_path):
    """Create a registry with sample projects."""
    config_dir = tmp_path / "config"
    registry = ProjectRegistry(config_dir=config_dir)

    # Add a project
    project_dir = tmp_path / "my-app"
    project_dir.mkdir()
    (project_dir / "package.json").write_text('{"name": "my-app"}')
    registry.add_project(str(project_dir))

    return registry


@pytest.fixture
def session_manager(registry_with_projects):
    """Create a session manager."""
    return SessionManager(registry=registry_with_projects)


@pytest.fixture
def mcp_server(registry_with_projects, session_manager):
    """Create a FastMCP server instance."""
    return create_server(registry_with_projects, session_manager)


class TestMCPTools:
    """Tests for MCP tool functions."""

    @pytest.mark.asyncio
    async def test_list_projects_empty(self, tmp_path):
        """Test list_projects returns empty message when no projects."""
        config_dir = tmp_path / "config"
        registry = ProjectRegistry(config_dir=config_dir)
        session_manager = SessionManager(registry=registry)
        server = create_server(registry, session_manager)

        # Access the tool function directly
        tool = server._tool_manager._tools["list_projects"]
        result = await tool.fn()

        data = json.loads(result)
        assert data["projects"] == []
        assert "No projects registered" in data["message"]

    @pytest.mark.asyncio
    async def test_list_projects_with_projects(
        self, registry_with_projects, session_manager, mcp_server
    ):
        """Test list_projects returns projects."""
        tool = mcp_server._tool_manager._tools["list_projects"]
        result = await tool.fn()

        data = json.loads(result)
        assert data["count"] == 1
        assert len(data["projects"]) == 1
        assert data["projects"][0]["name"] == "my-app"

    @pytest.mark.asyncio
    async def test_get_status(self, mcp_server):
        """Test get_status returns server status."""
        tool = mcp_server._tool_manager._tools["get_status"]
        result = await tool.fn()

        data = json.loads(result)
        assert "active_sessions" in data
        assert "registered_projects" in data
        assert "server_time" in data
        assert data["active_sessions"] == 0
        assert data["registered_projects"] == 1


class TestBearerAuthMiddleware:
    """Tests for BearerAuthMiddleware."""

    @pytest.mark.asyncio
    async def test_allows_valid_token(self):
        """Test middleware allows requests with valid token."""
        # Create mock app
        mock_app = AsyncMock()

        # Create middleware
        middleware = BearerAuthMiddleware(mock_app, "secret-token")

        # Create mock scope, receive, send
        scope = {
            "type": "http",
            "headers": [(b"authorization", b"Bearer secret-token")],
        }
        receive = AsyncMock()
        send = AsyncMock()

        # Call middleware
        await middleware(scope, receive, send)

        # App should be called
        mock_app.assert_called_once_with(scope, receive, send)
        # Send should not be called (no 401)
        send.assert_not_called()

    @pytest.mark.asyncio
    async def test_blocks_invalid_token(self):
        """Test middleware blocks requests with invalid token."""
        mock_app = AsyncMock()
        middleware = BearerAuthMiddleware(mock_app, "secret-token")

        scope = {
            "type": "http",
            "headers": [(b"authorization", b"Bearer wrong-token")],
        }
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        # App should NOT be called
        mock_app.assert_not_called()
        # Should send 401 response
        assert send.call_count == 2  # response.start and response.body
        # Check first call is 401
        first_call = send.call_args_list[0]
        assert first_call[0][0]["status"] == 401

    @pytest.mark.asyncio
    async def test_blocks_missing_token(self):
        """Test middleware blocks requests with no token."""
        mock_app = AsyncMock()
        middleware = BearerAuthMiddleware(mock_app, "secret-token")

        scope = {
            "type": "http",
            "headers": [],
        }
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        # App should NOT be called
        mock_app.assert_not_called()
        # Should send 401 response
        assert send.call_count == 2

    @pytest.mark.asyncio
    async def test_allows_non_http_requests(self):
        """Test middleware passes through non-HTTP requests."""
        mock_app = AsyncMock()
        middleware = BearerAuthMiddleware(mock_app, "secret-token")

        scope = {
            "type": "websocket",  # Not HTTP
            "headers": [],
        }
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        # App should be called (no auth check for websocket)
        mock_app.assert_called_once()
