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
from mcp.server.transport_security import TransportSecuritySettings

from .permissions import DEFAULT_PERMISSION
from .registry import ProjectRegistry
from .session import SessionManager

logger = logging.getLogger(__name__)

# Environment variable for bearer token authentication
AUTH_TOKEN_ENV = "PERPLEXITY_AGENT_TOKEN"


class HostRewriteMiddleware:
    """ASGI middleware to rewrite Host header for reverse proxy support."""

    def __init__(self, app: Any, target_host: str = "localhost") -> None:
        self.app = app
        self.target_host = target_host.encode()

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            # Rewrite headers to use localhost as host
            new_headers = []
            for name, value in scope.get("headers", []):
                if name == b"host":
                    new_headers.append((name, self.target_host))
                else:
                    new_headers.append((name, value))
            scope = dict(scope)
            scope["headers"] = new_headers

        await self.app(scope, receive, send)


class CORSMiddleware:
    """ASGI middleware for CORS support."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Debug: Log all incoming requests (print to stderr for visibility)
        import sys
        method = scope.get("method", "")
        path = scope.get("path", "")
        headers = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
        print(f"[REQUEST] {method} {path}", file=sys.stderr, flush=True)
        print(f"[HEADERS] {headers}", file=sys.stderr, flush=True)
        logger.info(f"[DEBUG] Incoming request: {method} {path}")
        logger.info(f"[DEBUG] Headers: {headers}")

        # Handle preflight OPTIONS requests
        if method == "OPTIONS":
            await self._send_preflight_response(send)
            return

        # Handle GET /mcp for server discovery
        if method == "GET" and path == "/mcp":
            await self._send_discovery_response(send)
            return

        # Handle GET / for health check (no auth required)
        if method == "GET" and path == "/":
            await self._send_health_response(send)
            return

        # For regular requests, wrap send to add CORS headers
        async def send_with_cors(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"access-control-allow-origin", b"*"),
                    (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
                    (b"access-control-allow-headers", b"*"),
                    (b"access-control-expose-headers", b"*"),
                ])
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_cors)

    async def _send_preflight_response(self, send: Any) -> None:
        """Send CORS preflight response."""
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"access-control-allow-origin", b"*"),
                (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
                (b"access-control-allow-headers", b"*"),
                (b"access-control-max-age", b"86400"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": b"",
        })

    async def _send_discovery_response(self, send: Any) -> None:
        """Send MCP server discovery response for GET /mcp."""
        import sys
        print("[DISCOVERY] GET /mcp - returning server info", file=sys.stderr, flush=True)

        discovery_info = json.dumps({
            "name": "perplexity-claude-agent",
            "version": "0.1.0",
            "protocol": "mcp",
            "capabilities": {
                "tools": True,
                "resources": False,
                "prompts": False,
            },
            "endpoints": {
                "mcp": "/mcp",
            },
        }).encode()

        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json"),
                (b"access-control-allow-origin", b"*"),
                (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
                (b"access-control-allow-headers", b"*"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": discovery_info,
        })

    async def _send_health_response(self, send: Any) -> None:
        """Send health check response for GET /."""
        import sys
        print("[HEALTH] GET / - server is healthy", file=sys.stderr, flush=True)

        health_info = json.dumps({
            "status": "healthy",
            "service": "perplexity-claude-agent",
            "version": "0.1.0",
            "mcp_endpoint": "/mcp",
        }).encode()

        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json"),
                (b"access-control-allow-origin", b"*"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": health_info,
        })


class BearerAuthMiddleware:
    """ASGI middleware for bearer token authentication.

    Supports both:
    - Authorization: Bearer <token>
    - x-api-key: <token>
    """

    def __init__(self, app: Any, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        import sys

        if scope["type"] == "http":
            # Extract headers
            headers = dict(scope.get("headers", []))
            path = scope.get("path", "")

            # Check Authorization: Bearer header
            auth = headers.get(b"authorization", b"").decode()
            if auth == f"Bearer {self.token}":
                print(f"[AUTH] ✓ Valid Bearer token for {path}", file=sys.stderr, flush=True)
                await self.app(scope, receive, send)
                return

            # Check x-api-key header (used by some clients like Perplexity)
            api_key = headers.get(b"x-api-key", b"").decode()
            if api_key == self.token:
                print(f"[AUTH] ✓ Valid x-api-key for {path}", file=sys.stderr, flush=True)
                await self.app(scope, receive, send)
                return

            # Log auth failure
            print(f"[AUTH] ✗ UNAUTHORIZED for {path}", file=sys.stderr, flush=True)
            print(f"[AUTH]   Authorization header: {auth[:20]}..." if auth else "[AUTH]   No Authorization header", file=sys.stderr, flush=True)
            print(f"[AUTH]   x-api-key header: {api_key[:20]}..." if api_key else "[AUTH]   No x-api-key header", file=sys.stderr, flush=True)

            # Return 401 Unauthorized
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    [b"content-type", b"text/plain"],
                    [b"access-control-allow-origin", b"*"],
                ],
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
        # Disable DNS rebinding protection to allow tunnel access
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
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

        import uvicorn

        # Get the ASGI app from FastMCP for streamable HTTP transport
        app = mcp.streamable_http_app()

        # Rewrite Host header for reverse proxy/tunnel support
        app = HostRewriteMiddleware(app, f"{host}:{port}")

        # Wrap with auth middleware if token is provided
        if token:
            app = BearerAuthMiddleware(app, token)

        # Always wrap with CORS middleware (outermost layer)
        app = CORSMiddleware(app)

        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
            proxy_headers=True,
            forwarded_allow_ips="*",
        )
        server = uvicorn.Server(config)
        await server.serve()
    finally:
        # Clean up all sessions on shutdown
        logger.info("Shutting down, closing all sessions...")
        await session_manager.close_all()
        logger.info("Server shutdown complete")


async def run_stdio_server(
    registry: ProjectRegistry,
    permission_preset: str = "safe",
) -> None:
    """Run the MCP server over stdio (for desktop apps).

    Args:
        registry: The project registry to use.
        permission_preset: Permission preset name.
    """
    # Create session manager
    session_manager = SessionManager(
        registry=registry,
        permission_preset=permission_preset,
    )

    # Create server
    mcp = create_server(registry, session_manager)

    try:
        # Start the session reaper
        await session_manager.start_reaper()

        # Run in stdio mode
        await mcp.run_stdio_async()
    finally:
        # Clean up all sessions on shutdown
        await session_manager.close_all()
