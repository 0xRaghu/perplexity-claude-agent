"""Session manager wrapping ClaudeSDKClient for persistent conversations.

This module manages Claude Code sessions with full context preservation,
allowing Perplexity Computer to maintain conversation state across multiple
MCP tool calls.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel

from .permissions import DEFAULT_PERMISSION, get_permission_mode
from .registry import ProjectRegistry

if TYPE_CHECKING:
    from claude_code_sdk import ClaudeSDKClient, ClaudeSDKError, ProcessError

logger = logging.getLogger(__name__)


class SessionInfo(BaseModel):
    """Metadata about an active session."""

    session_id: str
    """Unique identifier for this session."""

    project_name: str
    """Which project this session is for."""

    created_at: datetime
    """When the session was created."""

    last_activity: datetime
    """When the session was last used."""

    message_count: int = 0
    """Number of messages exchanged in this session."""

    is_active: bool = True
    """Whether the session is still active."""


class SessionManager:
    """Manages Claude Code sessions via ClaudeSDKClient.

    Each session is scoped to a project directory and maintains persistent
    conversation context across multiple queries.
    """

    def __init__(
        self,
        registry: ProjectRegistry,
        permission_preset: str = DEFAULT_PERMISSION,
        default_timeout: float = 300.0,
        idle_ttl: float = 600.0,
    ) -> None:
        """Initialize the session manager.

        Args:
            registry: The project registry for looking up project paths.
            permission_preset: Permission preset name ("default", "plan", "full").
            default_timeout: Default timeout in seconds for queries (default: 300).
            idle_ttl: Time in seconds before idle sessions are reaped (default: 600).
        """
        self._registry = registry
        self._sessions: dict[str, SessionInfo] = {}
        self._clients: dict[str, "ClaudeSDKClient"] = {}
        self._permission_mode = get_permission_mode(permission_preset)
        self._default_timeout = default_timeout
        self._idle_ttl = idle_ttl
        self._reaper_task: asyncio.Task | None = None

    async def start_reaper(self) -> None:
        """Start the background session reaper task.

        The reaper runs every 60 seconds and closes sessions that have been
        idle longer than idle_ttl.
        """
        if self._reaper_task is not None:
            return  # Already running

        async def _reaper_loop() -> None:
            while True:
                try:
                    await asyncio.sleep(60)  # Check every 60 seconds
                    await self._reap_idle_sessions()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Reaper error: {e}")

        self._reaper_task = asyncio.create_task(_reaper_loop())
        logger.info(f"Session reaper started (idle TTL: {self._idle_ttl}s)")

    async def stop_reaper(self) -> None:
        """Stop the background session reaper task."""
        if self._reaper_task is not None:
            self._reaper_task.cancel()
            try:
                await self._reaper_task
            except asyncio.CancelledError:
                pass
            self._reaper_task = None
            logger.info("Session reaper stopped")

    async def _reap_idle_sessions(self) -> None:
        """Close sessions that have been idle longer than idle_ttl."""
        now = datetime.now(timezone.utc)
        sessions_to_reap: list[tuple[str, str, float]] = []

        for session_id, session in list(self._sessions.items()):
            idle_seconds = (now - session.last_activity).total_seconds()
            if idle_seconds > self._idle_ttl:
                sessions_to_reap.append((session_id, session.project_name, idle_seconds))

        for session_id, project_name, idle_seconds in sessions_to_reap:
            idle_minutes = idle_seconds / 60
            logger.info(
                f"Reaped idle session {session_id} for project {project_name} "
                f"(idle for {idle_minutes:.1f}m)"
            )
            await self.close_session(session_id)

    async def create_session(
        self,
        project_name: str,
        session_id: str | None = None,
    ) -> SessionInfo:
        """Create a new Claude Code session for a project.

        Args:
            project_name: The name of the registered project.
            session_id: Optional session ID. Generated if not provided.

        Returns:
            SessionInfo with the session metadata.

        Raises:
            ValueError: If the project is not found in the registry.
        """
        # Import here to avoid import errors when SDK not installed
        from claude_code_sdk import ClaudeAgentOptions, ClaudeSDKClient

        # Look up project
        project = self._registry.get_project(project_name)
        if project is None:
            raise ValueError(f"Project '{project_name}' not found in registry")

        # Generate session ID if not provided
        if session_id is None:
            session_id = uuid.uuid4().hex[:12]

        # Check for duplicate session ID
        if session_id in self._sessions:
            raise ValueError(f"Session '{session_id}' already exists")

        # Create SDK options
        options = ClaudeAgentOptions(
            cwd=project.path,
            setting_sources=["project"],
            permission_mode=self._permission_mode,
        )

        # Create client and connect
        client = ClaudeSDKClient(options=options)
        try:
            await client.connect()
        except Exception as e:
            logger.error(f"Failed to start Claude Code session: {e}")
            raise RuntimeError(f"Failed to start Claude Code session: {e}") from e

        # Create session info
        now = datetime.now(timezone.utc)
        session_info = SessionInfo(
            session_id=session_id,
            project_name=project_name,
            created_at=now,
            last_activity=now,
            message_count=0,
            is_active=True,
        )

        # Store client and session
        self._clients[session_id] = client
        self._sessions[session_id] = session_info

        # Update registry last_accessed
        try:
            self._registry.update_last_accessed(project_name)
        except Exception as e:
            logger.warning(f"Failed to update last_accessed for {project_name}: {e}")

        logger.info(f"Created session {session_id} for project {project_name}")
        return session_info

    async def query(
        self,
        session_id: str,
        message: str,
        timeout: float | None = None,
    ) -> str:
        """Send a query to a Claude Code session.

        Args:
            session_id: The session to query.
            message: The message to send.
            timeout: Optional timeout in seconds. Uses default if not provided.

        Returns:
            The collected text response from Claude Code.

        Raises:
            ValueError: If the session is not found or inactive.
            asyncio.TimeoutError: If the query times out.
        """
        # Import message types
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        # Get session and client
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Session '{session_id}' not found")
        if not session.is_active:
            raise ValueError(f"Session '{session_id}' is no longer active")

        client = self._clients.get(session_id)
        if client is None:
            session.is_active = False
            raise ValueError(f"Client for session '{session_id}' not found")

        # Use provided timeout or default
        query_timeout = timeout if timeout is not None else self._default_timeout

        # Collect response text
        response_parts: list[str] = []

        try:
            # Wrap in timeout
            async def _do_query() -> None:
                # Send query
                await client.query(message)

                # Receive response messages
                async for msg in client.receive_response():
                    if isinstance(msg, AssistantMessage):
                        # Extract text from content blocks
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                response_parts.append(block.text)
                    elif isinstance(msg, ResultMessage):
                        # Log cost info if available
                        if msg.total_cost_usd is not None:
                            logger.debug(
                                f"Session {session_id} query cost: ${msg.total_cost_usd:.6f}"
                            )

            await asyncio.wait_for(_do_query(), timeout=query_timeout)

        except asyncio.TimeoutError:
            logger.warning(f"Session {session_id} query timed out after {query_timeout}s")
            # Clean up the zombie session
            try:
                await self.close_session(session_id)
            except Exception as close_err:
                logger.warning(f"Failed to close timed-out session {session_id}: {close_err}")
            raise
        except Exception as e:
            logger.error(f"Session {session_id} query failed: {e}")
            # Clean up the zombie session
            try:
                await self.close_session(session_id)
            except Exception as close_err:
                logger.warning(f"Failed to close failed session {session_id}: {close_err}")
            raise

        # Update session info
        session.last_activity = datetime.now(timezone.utc)
        session.message_count += 1

        return "".join(response_parts)

    async def close_session(self, session_id: str) -> bool:
        """Close a Claude Code session.

        Args:
            session_id: The session to close.

        Returns:
            True if the session was found and closed, False otherwise.
        """
        session = self._sessions.get(session_id)
        client = self._clients.get(session_id)

        if session is None:
            return False

        # Close the client
        if client is not None:
            try:
                await client.disconnect()
            except Exception as e:
                logger.warning(f"Error closing session {session_id}: {e}")

        # Remove from tracking
        self._sessions.pop(session_id, None)
        self._clients.pop(session_id, None)

        logger.info(f"Closed session {session_id}")
        return True

    def get_session(self, session_id: str) -> SessionInfo | None:
        """Get session info by ID.

        Args:
            session_id: The session to look up.

        Returns:
            SessionInfo if found, None otherwise.
        """
        return self._sessions.get(session_id)

    def list_sessions(self, project_name: str | None = None) -> list[SessionInfo]:
        """List all active sessions.

        Args:
            project_name: Optional filter by project name.

        Returns:
            List of SessionInfo objects.
        """
        sessions = list(self._sessions.values())

        if project_name is not None:
            sessions = [s for s in sessions if s.project_name == project_name]

        return sessions

    async def close_all(self) -> None:
        """Close all active sessions.

        Used during server shutdown to cleanly terminate all Claude Code
        subprocesses.
        """
        # Stop reaper first
        await self.stop_reaper()

        session_ids = list(self._sessions.keys())
        for session_id in session_ids:
            await self.close_session(session_id)
        logger.info(f"Closed {len(session_ids)} sessions")
