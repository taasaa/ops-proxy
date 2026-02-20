"""Tests for Telegram long polling module."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import httpx

from ops_proxy.telegram import TelegramLongPoller, send_message


class TestTelegramLongPoller:
    """Tests for TelegramLongPoller class."""

    @pytest.fixture
    def messages_file(self, tmp_path):
        """Create a temporary messages file."""
        return tmp_path / "inbox.json"

    @pytest.fixture
    def poller(self, messages_file):
        """Create a TelegramLongPoller instance."""
        return TelegramLongPoller(
            bot_token="test_token_123",
            messages_file=messages_file,
            timeout=30,
        )

    def test_get_base_url(self, poller):
        """Test that base URL is constructed correctly."""
        url = poller._get_base_url()
        assert url == "https://api.telegram.org/bottest_token_123"

    def test_load_offset_empty_file(self, poller, messages_file):
        """Test loading offset from empty file."""
        messages_file.write_text(json.dumps({"messages": []}))

        offset = poller._load_offset()

        assert offset == 0

    def test_load_offset_with_messages(self, poller, messages_file):
        """Test loading offset from file with messages."""
        data = {
            "messages": [
                {"update_id": 10, "text": "Hello"},
                {"update_id": 15, "text": "World"},
                {"update_id": 12, "text": "Middle"},
            ]
        }
        messages_file.write_text(json.dumps(data))

        offset = poller._load_offset()

        # Should be max update_id + 1
        assert offset == 16

    def test_load_offset_file_not_exists(self, poller, messages_file):
        """Test loading offset when file doesn't exist."""
        offset = poller._load_offset()
        assert offset == 0

    def test_load_offset_invalid_json(self, poller, messages_file):
        """Test loading offset with invalid JSON."""
        messages_file.write_text("not valid json")

        offset = poller._load_offset()
        assert offset == 0

    def test_save_messages(self, poller, messages_file):
        """Test saving messages to file."""
        messages = [
            {"update_id": 1, "text": "Hello", "chat": {"id": 123}},
        ]

        poller._save_messages(messages)

        assert messages_file.exists()
        data = json.loads(messages_file.read_text())
        assert "messages" in data
        assert len(data["messages"]) == 1


class TestTelegramPollerPoll:
    """Tests for poll method."""

    @pytest.fixture
    def messages_file(self, tmp_path):
        """Create a temporary messages file."""
        return tmp_path / "inbox.json"

    @patch("ops_proxy.telegram.httpx.Client")
    def test_poll_success(self, mock_client_class, messages_file):
        """Test successful polling."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "result": [
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 1,
                        "text": "Hello",
                        "chat": {"id": 123}
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        poller = TelegramLongPoller(
            bot_token="test_token",
            messages_file=messages_file,
            timeout=30,
        )

        messages = poller.poll()

        assert len(messages) == 1
        assert messages[0]["text"] == "Hello"
        assert messages[0]["update_id"] == 1

    @patch("ops_proxy.telegram.httpx.Client")
    def test_poll_no_updates(self, mock_client_class, messages_file):
        """Test polling with no new updates."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "result": []}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        poller = TelegramLongPoller(
            bot_token="test_token",
            messages_file=messages_file,
            timeout=30,
        )

        messages = poller.poll()

        assert len(messages) == 0

    @patch("ops_proxy.telegram.httpx.Client")
    def test_poll_api_error(self, mock_client_class, messages_file):
        """Test polling with API error."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": False, "description": "Bot blocked"}

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response

        mock_client_class.return_value = mock_client

        poller = TelegramLongPoller(
            bot_token="test_token",
            messages_file=messages_file,
            timeout=30,
        )

        messages = poller.poll()

        assert len(messages) == 0

    @patch("ops_proxy.telegram.httpx.Client")
    def test_poll_timeout(self, mock_client_class, messages_file):
        """Test polling timeout handling."""
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")
        mock_client_class.return_value = mock_client

        poller = TelegramLongPoller(
            bot_token="test_token",
            messages_file=messages_file,
            timeout=30,
        )

        messages = poller.poll()

        # Timeout should return empty list (normal behavior)
        assert len(messages) == 0

    @patch("ops_proxy.telegram.httpx.Client")
    def test_poll_updates_offset(self, mock_client_class, messages_file):
        """Test that poll updates offset correctly."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "result": [
                {"update_id": 5, "message": {"message_id": 1, "text": "Hello", "chat": {"id": 123}}},
                {"update_id": 10, "message": {"message_id": 2, "text": "World", "chat": {"id": 123}}},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        poller = TelegramLongPoller(
            bot_token="test_token",
            messages_file=messages_file,
            timeout=30,
        )

        messages = poller.poll()

        # Offset should be last update_id + 1
        assert poller._offset == 11


class TestTelegramPollerStartStop:
    """Tests for start and stop methods."""

    def test_start_sets_running(self, tmp_path):
        """Test that start sets running flag."""
        poller = TelegramLongPoller(
            bot_token="test_token",
            messages_file=tmp_path / "inbox.json",
            timeout=30,
        )

        poller.start()

        assert poller.running is True

    def test_stop_clears_running(self, tmp_path):
        """Test that stop clears running flag."""
        poller = TelegramLongPoller(
            bot_token="test_token",
            messages_file=tmp_path / "inbox.json",
            timeout=30,
        )

        poller.start()
        poller.stop()

        assert poller.running is False


class TestTelegramPollerClose:
    """Tests for close method."""

    def test_close_when_client_exists(self, tmp_path):
        """Test that close properly closes the client."""
        poller = TelegramLongPoller(
            bot_token="test_token",
            messages_file=tmp_path / "inbox.json",
            timeout=30,
        )

        # Create client
        client = poller._get_client()
        assert client is not None

        # Close
        poller.close()

        # Client should be None
        assert poller._client is None


class TestSendMessage:
    """Tests for send_message function."""

    @patch("ops_proxy.telegram.httpx.Client")
    def test_send_message_success(self, mock_client_class):
        """Test successful message sending."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "result": {
                "message_id": 123,
                "text": "Hello",
                "chat": {"id": 456}
            }
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        result = send_message("test_token", 456, "Hello")

        assert result is not None
        assert result["message_id"] == 123

    @patch("ops_proxy.telegram.httpx.Client")
    def test_send_message_api_error(self, mock_client_class):
        """Test message sending with API error."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": False, "description": "Chat not found"}

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response

        mock_client_class.return_value = mock_client

        result = send_message("test_token", 456, "Hello")

        assert result is None

    @patch("ops_proxy.telegram.httpx.Client")
    def test_send_message_network_error(self, mock_client_class):
        """Test message sending with network error."""
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.HTTPError("Connection error")
        mock_client_class.return_value = mock_client

        result = send_message("test_token", 456, "Hello")

        assert result is None
