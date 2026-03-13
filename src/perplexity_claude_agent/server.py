"""FastMCP Streamable HTTP server exposing Claude Code tools to Perplexity Computer.

This module implements the MCP server that Perplexity Computer connects to via
ngrok/cloudflared tunnel. It exposes tools for filesystem operations, code execution,
and session management.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP

from .permissions import DEFAULT_PERMISSION
from .registry import ProjectRegistry
from .session import SessionManager

logger = logging.getLogger(__name__)

# Environment variable for bearer token authentication
AUTH_TOKEN_ENV = "PERPLEXITY_AGENT_TOKEN"


class BearerAuthMiddleware:
    """ASGI middleware for bearer token authentication."""

    def __init__(self, app: Any, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            # Extract authorization header
            headers = dict(scope.get("headers", []))
            auth = headers.get(b"authorization", b"").decode()

            if auth != f"Bearer {self.token}":
                # Return 401 Unauthorized
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [[b"content-type", b"text/plain"]],
                })
                await send({
                    "type": "http.response.body",
                    "body": b"Unauthorized",
                })
                return

        await self.app(scope, receive, send)


def _json_response(data: Any) -> str:
    """Format data as pretty JSON string."""
    return json.dumps(data, indent=2, default=str)


def create_server(
    registry: ProjectRegistry,
    session_manager: SessionManager,
) -> FastMCP:
    """Create and configure the MCP server with all tools.

    Args:
        registry: The project registry for managing local projects.
        session_manager: The session manager for Claude Code sessions.

    Returns:
        Configured FastMCP server instance.
    """
    mcp = FastMCP(
        name="perplexity-claude-agent",
        stateless_http=False,  # We need stateful sessions
    )

    @mcp.tool()
    async def list_projects() -> str:
        """List all registered local projects available for Claude Code sessions.

        This is the first tool to call when starting a new task. It shows all
        local projects that have been registered, their tech stacks, and
        descriptions. Use this to discover what's available before opening
        a session.

        Returns a JSON array of project objects with: name, path, description,
        tech_stack, and is_default flag.
        """
        try:
            projects = registry.list_projects()
            default = registry.get_default()
            default_name = default.name if default else None

            result = [
                {
                    "name": p.name,
                    "path": p.path,
                    "description": p.description,
                    "tech_stack": p.tech_stack,
                    "is_default": p.name == default_name,
                }
                for p in projects
            ]

            if not result:
                return _json_response({
                    "projects": [],
                    "message": "No projects registered. Use the CLI to add projects: perplexity-claude-agent add-project <path>",
                })

            return _json_response({"projects": result, "count": len(result)})

        except Exception as e:
            logger.error(f"list_projects failed: {e}")
            return _json_response({"error": str(e)})

    @mcp.tool()
    async def open_project(project_name: str) -> str:
        """Open a new Claude Code session for a registered project.

        Creates a persistent Claude Code subprocess scoped to the project's
        directory. The session maintains full conversation context across
        multiple query_claude calls. Use this when you need to have a
        multi-turn conversation with Claude Code about a project.

        Args:
            project_name: The name of a registered project (from list_projects).

        Returns JSON with session_id, project_name, and status. Save the
        session_id for subsequent query_claude and close_session calls.
        """
        try:
            session = await session_manager.create_session(project_name)

            return _json_response({
                "session_id": session.session_id,
                "project_name": session.project_name,
                "status": "ready",
                "message": f"Claude Code session active for '{project_name}'. Use query_claude with this session_id to send messages.",
            })

        except ValueError as e:
            # Project not found or session already exists
            return _json_response({
                "error": str(e),
                "suggestion": "Use list_projects to see available projects.",
            })
        except Exception as e:
            logger.error(f"open_project failed: {e}")
            return _json_response({"error": f"Failed to open project: {e}"})

    @mcp.tool()
    async def query_claude(session_id: str, message: str) -> str:
        """Send a message to an active Claude Code session and get the response.

        This is the main tool for interacting with Claude Code. The session
        maintains full conversation history, so you can have multi-turn
        conversations. Claude Code has access to the project's filesystem,
        can read/write files, run commands, and perform complex development
        tasks.

        Args:
            session_id: The session ID from open_project.
            message: Your message or request to Claude Code.

        Returns Claude Code's response text. For complex tasks, Claude Code
        may describe what it did, show code changes, or ask clarifying
        questions.
        """
        try:
            response = await session_manager.query(session_id, message)
            return response

        except ValueError as e:
            # Session not found or inactive
            error_msg = str(e)
            return _json_response({
                "error": error_msg,
                "suggestion": "This session may have expired. Use open_project to create a new session.",
            })
        except asyncio.TimeoutError:
            return _json_response({
                "error": f"Query timed out for session {session_id}",
                "suggestion": "The request took too long. Try breaking it into smaller tasks, or open a new session.",
            })
        except Exception as e:
            logger.error(f"query_claude failed: {e}")
            return _json_response({
                "error": f"Query failed: {e}",
                "suggestion": "The session may be in a bad state. Try closing and reopening it.",
            })

    @mcp.tool()
    async def close_session(session_id: str) -> str:
        """Close a Claude Code session and free its resources.

        Call this when you're done with a session to clean up the Claude Code
        subprocess. Sessions that are left open continue to consume memory.

        Args:
            session_id: The session ID to close.

        Returns confirmation of closure.
        """
        try:
            closed = await session_manager.close_session(session_id)

            if closed:
                return _json_response({
                    "status": "closed",
                    "session_id": session_id,
                    "message": "Session closed successfully.",
                })
            else:
                return _json_response({
                    "status": "not_found",
                    "session_id": session_id,
                    "message": "Session was not found (may have already been closed).",
                })

        except Exception as e:
            logger.error(f"close_session failed: {e}")
            return _json_response({"error": f"Failed to close session: {e}"})

    @mcp.tool()
    async def get_status() -> str:
        """Get the current server status including active sessions.

        Returns information about the server state: number of active sessions,
        details about each session (id, project, message count, last activity),
        and number of registered projects. Useful for checking what's currently
        running.
        """
        try:
            sessions = session_manager.list_sessions()
            projects = registry.list_projects()

            session_summaries = [
                {
                    "session_id": s.session_id,
                    "project_name": s.project_name,
                    "message_count": s.message_count,
                    "last_activity": s.last_activity.isoformat(),
                    "is_active": s.is_active,
                }
                for s in sessions
            ]

            return _json_response({
                "active_sessions": len(sessions),
                "sessions": session_summaries,
                "registered_projects": len(projects),
                "server_time": datetime.now(timezone.utc).isoformat(),
            })

        except Exception as e:
            logger.error(f"get_status failed: {e}")
            return _json_response({"error": f"Failed to get status: {e}"})

    @mcp.tool()
    async def execute_quick(project_name: str, message: str) -> str:
        """Execute a one-off Claude Code task without session management.

        This is a convenience tool that opens a session, sends one message,
        gets the response, and closes the session — all in one call. Use this
        for simple, standalone tasks that don't need conversation continuity.

        For multi-turn conversations, use open_project + query_claude instead.

        Args:
            project_name: The name of a registered project.
            message: Your message or request to Claude Code.

        Returns Claude Code's response, or an error if something failed.
        """
        session_id = None
        try:
            # Open session
            session = await session_manager.create_session(project_name)
            session_id = session.session_id

            # Send query
            response = await session_manager.query(session_id, message)

            # Close session
            await session_manager.close_session(session_id)

            return response

        except ValueError as e:
            # Project not found
            return _json_response({
                "error": str(e),
                "suggestion": "Use list_projects to see available projects.",
            })
        except asyncio.TimeoutError:
            # Session already closed by query() on timeout
            return _json_response({
                "error": "Query timed out",
                "suggestion": "The request took too long. Try breaking it into smaller tasks.",
            })
        except Exception as e:
            logger.error(f"execute_quick failed: {e}")
            # Try to close the session if it was opened
            if session_id:
                try:
                    await session_manager.close_session(session_id)
                except Exception:
                    pass
            return _json_response({"error": f"Execution failed: {e}"})

    return mcp


def get_auth_token() -> str | None:
    """Get the authentication token from environment."""
    return os.environ.get(AUTH_TOKEN_ENV)


async def run_server(
    host: str = "0.0.0.0",
    port: int = 8765,
    registry: ProjectRegistry | None = None,
    permission_preset: str = DEFAULT_PERMISSION,
    auth_token: str | None = None,
) -> None:
    """Start the MCP server.

    Args:
        host: Host to bind to (default: 0.0.0.0).
        port: Port to listen on (default: 8765).
        registry: Optional ProjectRegistry. Creates one if not provided.
        permission_preset: Permission preset for Claude Code sessions.
        auth_token: Optional bearer token for authentication. If not provided,
            checks PERPLEXITY_AGENT_TOKEN env var.
    """
    # Create registry if not provided
    if registry is None:
        registry = ProjectRegistry()

    # Create session manager
    session_manager = SessionManager(
        registry=registry,
        permission_preset=permission_preset,
    )

    # Create server
    mcp = create_server(registry, session_manager)

    # Check for auth token
    token = auth_token or get_auth_token()
    if token:
        logger.info("Bearer token authentication enabled")
    else:
        logger.warning(
            f"WARNING: No {AUTH_TOKEN_ENV} set. Server is accessible without "
            f"authentication. Set {AUTH_TOKEN_ENV} env var for security."
        )

    logger.info(f"Starting MCP server on {host}:{port}")
    logger.info(f"Permission preset: {permission_preset}")
    logger.info(f"Registered projects: {len(registry.list_projects())}")

    try:
        # Start the session reaper
        await session_manager.start_reaper()

        # Get the ASGI app from FastMCP
        # Note: We need to access the underlying app to wrap with middleware
        # FastMCP's run_async handles this internally, so we use uvicorn directly
        # when auth is needed
        if token:
            import uvicorn

            # Create the ASGI app with auth middleware
            app = mcp.get_app()
            authed_app = BearerAuthMiddleware(app, token)

            config = uvicorn.Config(
                authed_app,
                host=host,
                port=port,
                log_level="info",
            )
            server = uvicorn.Server(config)
            await server.serve()
        else:
            # Run without auth middleware
            await mcp.run_async(
                transport="streamable-http",
                host=host,
                port=port,
            )
    finally:
        # Clean up all sessions on shutdown
        logger.info("Shutting down, closing all sessions...")
        await session_manager.close_all()
        logger.info("Server shutdown complete")
