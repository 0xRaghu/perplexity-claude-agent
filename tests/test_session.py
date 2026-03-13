"""Tests for session manager with mocked ClaudeSDKClient."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from perplexity_claude_agent.registry import ProjectRegistry
from perplexity_claude_agent.session import SessionInfo, SessionManager


# NOTE: session.py imports AssistantMessage/ResultMessage/TextBlock inside query()
# at call time via deferred imports. Our mocks work because mock_client yields
# these mock types and tests validate final output strings, not type branching.
# If those imports are ever moved to top-level in session.py, update test
# patching to target perplexity_claude_agent.session.<ClassName> directly.


# Mock SDK types
class MockTextBlock:
    """Mock for TextBlock."""

    def __init__(self, text: str):
        self.text = text


class MockAssistantMessage:
    """Mock for AssistantMessage."""

    def __init__(self, text: str):
        self.content = [MockTextBlock(text)]


class MockResultMessage:
    """Mock for ResultMessage."""

    def __init__(self):
        self.total_cost_usd = 0.001


@pytest.fixture
def mock_client():
    """Create a mock ClaudeSDKClient."""
    client = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.query = AsyncMock()

    # Mock receive_response as an async iterator
    async def mock_receive():
        yield MockAssistantMessage("Hello from Claude")
        yield MockResultMessage()

    client.receive_response = mock_receive
    return client


@pytest.fixture
def registry_with_project(tmp_path):
    """Create a registry with a sample project."""
    config_dir = tmp_path / "config"
    registry = ProjectRegistry(config_dir=config_dir)

    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    (project_dir / "README.md").write_text("# Test\n")

    registry.add_project(str(project_dir))
    return registry


class TestSessionManager:
    """Tests for SessionManager class."""

    @pytest.mark.asyncio
    async def test_create_session(self, mock_client, registry_with_project):
        """Test creating a session calls connect() and returns SessionInfo."""
        manager = SessionManager(registry=registry_with_project)

        with patch(
            "perplexity_claude_agent.session.ClaudeSDKClient",
            return_value=mock_client,
        ):
            with patch("perplexity_claude_agent.session.ClaudeAgentOptions"):
                session = await manager.create_session("test-project")

        assert session.project_name == "test-project"
        assert session.is_active is True
        assert session.message_count == 0
        mock_client.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_session_unknown_project(self, tmp_path):
        """Test that creating a session for unknown project raises ValueError."""
        config_dir = tmp_path / "config"
        registry = ProjectRegistry(config_dir=config_dir)
        manager = SessionManager(registry=registry)

        with pytest.raises(ValueError, match="not found in registry"):
            await manager.create_session("nonexistent")

    @pytest.mark.asyncio
    async def test_query_session(self, mock_client, registry_with_project):
        """Test querying a session returns response text."""
        manager = SessionManager(registry=registry_with_project)

        with patch(
            "perplexity_claude_agent.session.ClaudeSDKClient",
            return_value=mock_client,
        ):
            with patch("perplexity_claude_agent.session.ClaudeAgentOptions"):
                # Need to mock the types for isinstance checks
                with patch(
                    "perplexity_claude_agent.session.AssistantMessage",
                    MockAssistantMessage,
                ):
                    with patch(
                        "perplexity_claude_agent.session.ResultMessage",
                        MockResultMessage,
                    ):
                        with patch(
                            "perplexity_claude_agent.session.TextBlock",
                            MockTextBlock,
                        ):
                            session = await manager.create_session("test-project")
                            response = await manager.query(
                                session.session_id, "Hello"
                            )

        assert response == "Hello from Claude"
        mock_client.query.assert_called_once_with("Hello")

    @pytest.mark.asyncio
    async def test_query_updates_activity(self, mock_client, registry_with_project):
        """Test that query updates last_activity and message_count."""
        manager = SessionManager(registry=registry_with_project)

        with patch(
            "perplexity_claude_agent.session.ClaudeSDKClient",
            return_value=mock_client,
        ):
            with patch("perplexity_claude_agent.session.ClaudeAgentOptions"):
                with patch(
                    "perplexity_claude_agent.session.AssistantMessage",
                    MockAssistantMessage,
                ):
                    with patch(
                        "perplexity_claude_agent.session.ResultMessage",
                        MockResultMessage,
                    ):
                        with patch(
                            "perplexity_claude_agent.session.TextBlock",
                            MockTextBlock,
                        ):
                            session = await manager.create_session("test-project")
                            original_activity = session.last_activity

                            await manager.query(session.session_id, "Hello")

                            updated = manager.get_session(session.session_id)

        assert updated is not None
        assert updated.message_count == 1
        assert updated.last_activity >= original_activity

    @pytest.mark.asyncio
    async def test_close_session(self, mock_client, registry_with_project):
        """Test closing a session calls disconnect() and removes from tracking."""
        manager = SessionManager(registry=registry_with_project)

        with patch(
            "perplexity_claude_agent.session.ClaudeSDKClient",
            return_value=mock_client,
        ):
            with patch("perplexity_claude_agent.session.ClaudeAgentOptions"):
                session = await manager.create_session("test-project")
                session_id = session.session_id

                closed = await manager.close_session(session_id)

        assert closed is True
        assert manager.get_session(session_id) is None
        mock_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_nonexistent_session(self, registry_with_project):
        """Test closing a nonexistent session returns False."""
        manager = SessionManager(registry=registry_with_project)

        closed = await manager.close_session("nonexistent")

        assert closed is False

    @pytest.mark.asyncio
    async def test_list_sessions(self, mock_client, registry_with_project):
        """Test listing all sessions."""
        manager = SessionManager(registry=registry_with_project)

        with patch(
            "perplexity_claude_agent.session.ClaudeSDKClient",
            return_value=mock_client,
        ):
            with patch("perplexity_claude_agent.session.ClaudeAgentOptions"):
                await manager.create_session("test-project", session_id="session1")
                await manager.create_session("test-project", session_id="session2")

        sessions = manager.list_sessions()

        assert len(sessions) == 2

    @pytest.mark.asyncio
    async def test_list_sessions_filter_by_project(
        self, mock_client, registry_with_project, tmp_path
    ):
        """Test filtering sessions by project name."""
        # Add a second project
        project2 = tmp_path / "project2"
        project2.mkdir()
        (project2 / "README.md").write_text("# Test 2\n")
        registry_with_project.add_project(str(project2))

        manager = SessionManager(registry=registry_with_project)

        with patch(
            "perplexity_claude_agent.session.ClaudeSDKClient",
            return_value=mock_client,
        ):
            with patch("perplexity_claude_agent.session.ClaudeAgentOptions"):
                await manager.create_session("test-project", session_id="s1")
                await manager.create_session("project2", session_id="s2")

        # Filter by first project
        sessions = manager.list_sessions(project_name="test-project")
        assert len(sessions) == 1
        assert sessions[0].project_name == "test-project"

    @pytest.mark.asyncio
    async def test_reaper_closes_idle_sessions(
        self, mock_client, registry_with_project
    ):
        """Test that the reaper closes idle sessions."""
        # Use a very short TTL for testing
        manager = SessionManager(
            registry=registry_with_project,
            idle_ttl=0.1,  # 100ms
        )

        with patch(
            "perplexity_claude_agent.session.ClaudeSDKClient",
            return_value=mock_client,
        ):
            with patch("perplexity_claude_agent.session.ClaudeAgentOptions"):
                session = await manager.create_session("test-project")
                session_id = session.session_id

                # Wait for session to become idle
                await asyncio.sleep(0.2)

                # Manually trigger reap (normally done by background task)
                await manager._reap_idle_sessions()

        # Session should be closed
        assert manager.get_session(session_id) is None

    @pytest.mark.asyncio
    async def test_close_all_stops_reaper(self, registry_with_project):
        """Test that close_all stops the reaper task."""
        manager = SessionManager(registry=registry_with_project)

        await manager.start_reaper()
        assert manager._reaper_task is not None

        await manager.close_all()

        assert manager._reaper_task is None
