"""Tests for OpenClaw notifier module."""

import pytest
from unittest.mock import MagicMock, patch
import httpx

from ops_proxy.notifier import OpenClawNotifier, notify_openclaw


class TestOpenClawNotifier:
    """Tests for OpenClawNotifier class."""

    def test_is_configured_when_configured(self):
        """Test is_configured returns True when URL and token are set."""
        notifier = OpenClawNotifier(
            hook_url="http://localhost:18790/hook/agent",
            hook_token="secret_token"
        )

        assert notifier.is_configured() is True

    def test_is_configured_missing_url(self):
        """Test is_configured returns False when URL is missing."""
        notifier = OpenClawNotifier(
            hook_url=None,
            hook_token="secret_token"
        )

        assert notifier.is_configured() is False

    def test_is_configured_missing_token(self):
        """Test is_configured returns False when token is missing."""
        notifier = OpenClawNotifier(
            hook_url="http://localhost:18790/hook/agent",
            hook_token=None
        )

        assert notifier.is_configured() is False

    def test_is_configured_both_missing(self):
        """Test is_configured returns False when both are missing."""
        notifier = OpenClawNotifier(
            hook_url=None,
            hook_token=None
        )

        assert notifier.is_configured() is False


class TestNotifyInbox:
    """Tests for notify_inbox method."""

    def test_notify_inbox_no_url(self):
        """Test that notification is skipped when URL is not configured."""
        notifier = OpenClawNotifier(hook_url=None, hook_token="token")

        result = notifier.notify_inbox(123, 456, "Hello")

        assert result is False

    def test_notify_inbox_no_token(self):
        """Test that notification is skipped when token is not configured."""
        notifier = OpenClawNotifier(hook_url="http://localhost:18790/hook/agent", hook_token=None)

        result = notifier.notify_inbox(123, 456, "Hello")

        assert result is False

    @patch("ops_proxy.notifier.httpx.Client")
    def test_notify_inbox_success(self, mock_client_class):
        """Test successful notification."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        notifier = OpenClawNotifier(
            hook_url="http://localhost:18790/hook/agent",
            hook_token="secret_token"
        )

        result = notifier.notify_inbox(123, 456, "Test message")

        assert result is True
        mock_client.post.assert_called_once()

        # Verify the URL was converted from /agent to /wake
        call_args = mock_client.post.call_args
        assert "/wake" in call_args[0][0]

    @patch("ops_proxy.notifier.httpx.Client")
    def test_notify_inbox_timeout(self, mock_client_class):
        """Test handling of timeout."""
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.TimeoutException("Timeout")
        mock_client_class.return_value = mock_client

        notifier = OpenClawNotifier(
            hook_url="http://localhost:18790/hook/agent",
            hook_token="secret_token"
        )

        result = notifier.notify_inbox(123, 456, "Test message")

        assert result is False

    @patch("ops_proxy.notifier.httpx.Client")
    def test_notify_inbox_http_error(self, mock_client_class):
        """Test handling of HTTP error."""
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.HTTPError("Connection error")
        mock_client_class.return_value = mock_client

        notifier = OpenClawNotifier(
            hook_url="http://localhost:18790/hook/agent",
            hook_token="secret_token"
        )

        result = notifier.notify_inbox(123, 456, "Test message")

        assert result is False


class TestNotifierClose:
    """Tests for close method."""

    def test_close_when_client_exists(self):
        """Test that close properly closes the client."""
        notifier = OpenClawNotifier(
            hook_url="http://localhost:18790/hook/agent",
            hook_token="secret_token"
        )

        # Create client
        client = notifier._get_client()
        assert client is not None

        # Close
        notifier.close()

        # Client should be None
        assert notifier._client is None

    def test_close_when_client_none(self):
        """Test that close works when client doesn't exist."""
        notifier = OpenClawNotifier(
            hook_url="http://localhost:18790/hook/agent",
            hook_token="secret_token"
        )

        # Should not raise
        notifier.close()
        assert notifier._client is None


class TestNotifyOpenclawFunction:
    """Tests for notify_openclaw convenience function."""

    @patch("ops_proxy.notifier.OpenClawNotifier")
    def test_notify_openclaw_calls_notifier(self, mock_notifier_class):
        """Test that notify_openclaw creates and uses notifier."""
        mock_notifier = MagicMock()
        mock_notifier.notify_inbox.return_value = True
        mock_notifier_class.return_value = mock_notifier

        result = notify_openclaw(
            hook_url="http://localhost:18790/hook/agent",
            hook_token="secret_token",
            message_text="Test message",
            chat_id=123
        )

        assert result is True
        mock_notifier_class.assert_called_once_with(
            "http://localhost:18790/hook/agent",
            "secret_token"
        )
        mock_notifier.notify_inbox.assert_called_once()
        mock_notifier.close.assert_called_once()

    @patch("ops_proxy.notifier.OpenClawNotifier")
    def test_notify_openclaw_extracts_update_id(self, mock_notifier_class):
        """Test that update_id is extracted from message_text."""
        mock_notifier = MagicMock()
        mock_notifier.notify_inbox.return_value = True
        mock_notifier_class.return_value = mock_notifier

        notify_openclaw(
            hook_url="http://localhost:18790/hook/agent",
            hook_token="secret_token",
            message_text="New message: read from inbox update_id=12345",
            chat_id=None
        )

        # Should call with update_id=12345
        mock_notifier.notify_inbox.assert_called_once_with(12345, 0, "New message: read from inbox update_id=12345")
