"""Tests for unified format (command/payload) translation in HTTP client."""

import os
import pytest
from unittest.mock import MagicMock, patch, mock_open
from datetime import datetime, timezone

from ops_proxy.http_client import HTTPClient, Request, Response
from ops_proxy.config import Config
from ops_proxy.rules import RulesEngine


class TestUnifiedFormatTextMessage:
    """Tests for unified format text message translation."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create a test config with bot token."""
        config = Config(tmp_path / "data")
        config._config = {
            "allowed_urls": [
                r"^https://api\.telegram\.org/",
            ],
            "max_body_size": 1048576,
            "request_timeout": 30,
        }
        config._config["token_env"] = "TEST_TOKEN"
        return config

    @pytest.fixture
    def rules(self, config):
        """Create a RulesEngine instance."""
        return RulesEngine(config)

    @patch.dict(os.environ, {"TEST_TOKEN": "mock_bot_token_123"})
    def test_translate_unified_format_text_message(self, config, rules):
        """Test that unified format with text translates to Telegram sendMessage."""
        http_client = HTTPClient(config, rules)

        request = Request(
            id="test-1",
            method="POST",
            url="https://api.telegram.org/bot<token>/sendMessage",
            headers={},
            body={
                "id": "test-1",
                "command": "send",
                "payload": {
                    "chat_id": "835708206",
                    "text": "Hello world",
                },
            },
            created_at=datetime.now(timezone.utc),
        )

        result = http_client._translate_unified_format(request)

        assert result is not None
        translated_request, files = result

        # Should translate to sendMessage endpoint
        assert "sendMessage" in translated_request.url
        assert "mock_bot_token_123" in translated_request.url

        # Body should have chat_id and text
        assert translated_request.body["chat_id"] == "835708206"
        assert translated_request.body["text"] == "Hello world"

        # No files for text message
        assert files is None

    @patch.dict(os.environ, {"TEST_TOKEN": "mock_bot_token_123"})
    def test_translate_unified_format_text_with_markdown(self, config, rules):
        """Test unified format with markdown parse mode."""
        http_client = HTTPClient(config, rules)

        request = Request(
            id="test-2",
            method="POST",
            url="",
            headers={},
            body={
                "id": "test-2",
                "command": "send",
                "payload": {
                    "chat_id": "835708206",
                    "text": "Hello *bold* world",
                    "format": "markdown",
                },
            },
            created_at=datetime.now(timezone.utc),
        )

        result = http_client._translate_unified_format(request)

        assert result is not None
        translated_request, files = result

        assert translated_request.body["parse_mode"] == "Markdown"
        assert files is None

    @patch.dict(os.environ, {"TEST_TOKEN": "mock_bot_token_123"})
    def test_translate_unified_format_text_with_html(self, config, rules):
        """Test unified format with html parse mode."""
        http_client = HTTPClient(config, rules)

        request = Request(
            id="test-3",
            method="POST",
            url="",
            headers={},
            body={
                "id": "test-3",
                "command": "send",
                "payload": {
                    "chat_id": "835708206",
                    "text": "Hello <b>bold</b> world",
                    "format": "html",
                },
            },
            created_at=datetime.now(timezone.utc),
        )

        result = http_client._translate_unified_format(request)

        assert result is not None
        translated_request, files = result

        assert translated_request.body["parse_mode"] == "Html"
        assert files is None

    @patch.dict(os.environ, {"TEST_TOKEN": "mock_bot_token_123"})
    def test_translate_unified_format_text_plain_default(self, config, rules):
        """Test unified format defaults to plain (no parse_mode)."""
        http_client = HTTPClient(config, rules)

        request = Request(
            id="test-4",
            method="POST",
            url="",
            headers={},
            body={
                "id": "test-4",
                "command": "send",
                "payload": {
                    "chat_id": "835708206",
                    "text": "Plain text",
                },
            },
            created_at=datetime.now(timezone.utc),
        )

        result = http_client._translate_unified_format(request)

        assert result is not None
        translated_request, files = result

        # No parse_mode for plain text
        assert "parse_mode" not in translated_request.body
        assert files is None


class TestUnifiedFormatDocumentUpload:
    """Tests for unified format document upload translation."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create a test config with bot token."""
        config = Config(tmp_path / "data")
        config._config = {
            "allowed_urls": [
                r"^https://api\.telegram\.org/",
            ],
            "max_body_size": 1048576,
            "request_timeout": 30,
        }
        config._config["token_env"] = "TEST_TOKEN"
        return config

    @pytest.fixture
    def rules(self, config):
        """Create a RulesEngine instance."""
        return RulesEngine(config)

    @patch.dict(os.environ, {"TEST_TOKEN": "mock_bot_token_123"})
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_bytes")
    def test_translate_unified_format_document(self, mock_read, mock_exists, config, rules):
        """Test that unified format with path translates to Telegram sendDocument."""
        mock_exists.return_value = True
        mock_read.return_value = b"file content here"

        http_client = HTTPClient(config, rules)

        request = Request(
            id="doc-test-1",
            method="POST",
            url="",
            headers={},
            body={
                "id": "doc-test-1",
                "command": "send",
                "payload": {
                    "chat_id": "835708206",
                    "path": "/tmp/test.pdf",
                },
            },
            created_at=datetime.now(timezone.utc),
        )

        result = http_client._translate_unified_format(request)

        assert result is not None
        translated_request, files = result

        # Should translate to sendDocument endpoint
        assert "sendDocument" in translated_request.url
        assert "mock_bot_token_123" in translated_request.url

        # Body should have chat_id
        assert translated_request.body["chat_id"] == "835708206"

        # Files should be present
        assert files is not None
        assert "document" in files

    @patch.dict(os.environ, {"TEST_TOKEN": "mock_bot_token_123"})
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_bytes")
    def test_translate_unified_format_document_with_caption(self, mock_read, mock_exists, config, rules):
        """Test document upload with caption text."""
        mock_exists.return_value = True
        mock_read.return_value = b"file content here"

        http_client = HTTPClient(config, rules)

        request = Request(
            id="doc-test-2",
            method="POST",
            url="",
            headers={},
            body={
                "id": "doc-test-2",
                "command": "send",
                "payload": {
                    "chat_id": "835708206",
                    "text": "Here is the document",
                    "path": "/tmp/test.pdf",
                },
            },
            created_at=datetime.now(timezone.utc),
        )

        result = http_client._translate_unified_format(request)

        assert result is not None
        translated_request, files = result

        # Caption should be in body
        assert translated_request.body["caption"] == "Here is the document"
        assert files is not None


class TestUnifiedFormatErrorHandling:
    """Tests for unified format error handling."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create a test config with bot token."""
        config = Config(tmp_path / "data")
        config._config = {
            "allowed_urls": [
                r"^https://api\.telegram\.org/",
            ],
            "max_body_size": 1048576,
            "request_timeout": 30,
        }
        config._config["token_env"] = "TEST_TOKEN"
        return config

    @pytest.fixture
    def rules(self, config):
        """Create a RulesEngine instance."""
        return RulesEngine(config)

    @patch.dict(os.environ, {"TEST_TOKEN": "mock_bot_token_123"})
    def test_translate_missing_chat_id(self, config, rules):
        """Test error when chat_id is missing."""
        http_client = HTTPClient(config, rules)

        request = Request(
            id="error-test-1",
            method="POST",
            url="",
            headers={},
            body={
                "id": "error-test-1",
                "command": "send",
                "payload": {
                    "text": "Hello",
                    # chat_id missing
                },
            },
            created_at=datetime.now(timezone.utc),
        )

        result = http_client._translate_unified_format(request)

        # Should return None (not a unified format request)
        assert result is None

    @patch.dict(os.environ, {"TEST_TOKEN": "mock_bot_token_123"})
    def test_translate_missing_text_and_path(self, config, rules):
        """Test error when both text and path are missing."""
        http_client = HTTPClient(config, rules)

        request = Request(
            id="error-test-2",
            method="POST",
            url="",
            headers={},
            body={
                "id": "error-test-2",
                "command": "send",
                "payload": {
                    "chat_id": "835708206",
                    # text missing
                    # path missing
                },
            },
            created_at=datetime.now(timezone.utc),
        )

        result = http_client._translate_unified_format(request)

        # Should return None
        assert result is None

    @patch.dict(os.environ, {"TEST_TOKEN": "mock_bot_token_123"})
    @patch("pathlib.Path.exists")
    def test_translate_file_not_found(self, mock_exists, config, rules):
        """Test error when file path does not exist."""
        mock_exists.return_value = False

        http_client = HTTPClient(config, rules)

        request = Request(
            id="error-test-3",
            method="POST",
            url="",
            headers={},
            body={
                "id": "error-test-3",
                "command": "send",
                "payload": {
                    "chat_id": "835708206",
                    "path": "/nonexistent/file.pdf",
                },
            },
            created_at=datetime.now(timezone.utc),
        )

        result = http_client._translate_unified_format(request)

        # Should return None
        assert result is None

    def test_translate_no_bot_token(self, tmp_path):
        """Test error when no bot token is configured."""
        config = Config(tmp_path / "data")
        config._config = {
            "allowed_urls": [
                r"^https://api\.telegram\.org/",
            ],
            "max_body_size": 1048576,
            "request_timeout": 30,
        }
        # No token env set

        rules = RulesEngine(config)
        http_client = HTTPClient(config, rules)

        request = Request(
            id="error-test-4",
            method="POST",
            url="",
            headers={},
            body={
                "id": "error-test-4",
                "command": "send",
                "payload": {
                    "chat_id": "835708206",
                    "text": "Hello",
                },
            },
            created_at=datetime.now(timezone.utc),
        )

        result = http_client._translate_unified_format(request)

        # Should return None
        assert result is None


class TestUnifiedFormatNonUnified:
    """Tests for non-unified format requests (should not be translated)."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create a test config."""
        config = Config(tmp_path / "data")
        config._config = {
            "allowed_urls": [
                r"^https://api\.telegram\.org/",
            ],
            "max_body_size": 1048576,
            "request_timeout": 30,
        }
        return config

    @pytest.fixture
    def rules(self, config):
        """Create a RulesEngine instance."""
        return RulesEngine(config)

    def test_non_unified_format_body(self, config, rules):
        """Test that non-unified format returns None."""
        http_client = HTTPClient(config, rules)

        request = Request(
            id="non-unified-1",
            method="POST",
            url="https://api.telegram.org/bot<token>/sendMessage",
            headers={},
            body={"chat_id": "835708206", "text": "Hello"},
            created_at=datetime.now(timezone.utc),
        )

        result = http_client._translate_unified_format(request)

        # Should return None for non-unified format
        assert result is None

    def test_non_unified_format_no_command(self, config, rules):
        """Test that request without command returns None."""
        http_client = HTTPClient(config, rules)

        request = Request(
            id="non-unified-2",
            method="POST",
            url="https://api.telegram.org/bot<token>/sendMessage",
            headers={},
            body={
                "id": "non-unified-2",
                "payload": {
                    "chat_id": "835708206",
                    "text": "Hello",
                },
                # command missing
            },
            created_at=datetime.now(timezone.utc),
        )

        result = http_client._translate_unified_format(request)

        assert result is None

    def test_non_unified_format_no_payload(self, config, rules):
        """Test that request without payload returns None."""
        http_client = HTTPClient(config, rules)

        request = Request(
            id="non-unified-3",
            method="POST",
            url="https://api.telegram.org/bot<token>/sendMessage",
            headers={},
            body={
                "id": "non-unified-3",
                "command": "send",
                # payload missing
            },
            created_at=datetime.now(timezone.utc),
        )

        result = http_client._translate_unified_format(request)

        assert result is None


class TestUnifiedFormatExecute:
    """Tests for execute() with unified format end-to-end."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create a test config."""
        config = Config(tmp_path / "data")
        config._config = {
            "allowed_urls": [
                r"^https://api\.telegram\.org/",
            ],
            "max_body_size": 1048576,
            "request_timeout": 30,
        }
        config._config["token_env"] = "TEST_TOKEN"
        return config

    @pytest.fixture
    def rules(self, config):
        """Create a RulesEngine instance."""
        return RulesEngine(config)

    @patch.dict(os.environ, {"TEST_TOKEN": "mock_bot_token_123"})
    def test_execute_unified_format_text_message(self, config, rules):
        """Test execute() with unified format text message."""
        http_client = HTTPClient(config, rules)

        request = Request(
            id="exec-test-1",
            method="POST",
            url="",  # Will be translated
            headers={},
            body={
                "id": "exec-test-1",
                "command": "send",
                "payload": {
                    "chat_id": "835708206",
                    "text": "Test message",
                },
            },
            created_at=datetime.now(timezone.utc),
        )

        with patch.object(http_client, '_get_client') as mock_get_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = '{"ok": true, "result": {"message_id": 123}}'
            mock_response.json.return_value = {"ok": True, "result": {"message_id": 123}}

            mock_client = MagicMock()
            mock_client.request.return_value = mock_response
            mock_get_client.return_value = mock_client

            response = http_client.execute(request)

            # Should succeed
            assert response.status == 200
            assert response.body["ok"] is True
            assert response.error is None

            # Verify the API was called with correct endpoint
            call_args = mock_client.request.call_args
            assert "sendMessage" in call_args[1]["url"]

    @patch.dict(os.environ, {"TEST_TOKEN": "mock_bot_token_123"})
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_bytes")
    def test_execute_unified_format_document(self, mock_read, mock_exists, config, rules):
        """Test execute() with unified format document upload."""
        mock_exists.return_value = True
        mock_read.return_value = b"test file content"

        http_client = HTTPClient(config, rules)

        request = Request(
            id="exec-test-2",
            method="POST",
            url="",  # Will be translated
            headers={},
            body={
                "id": "exec-test-2",
                "command": "send",
                "payload": {
                    "chat_id": "835708206",
                    "text": "Document attached",
                    "path": "/tmp/test.pdf",
                },
            },
            created_at=datetime.now(timezone.utc),
        )

        with patch.object(http_client, '_get_client') as mock_get_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = '{"ok": true}'
            mock_response.json.return_value = {"ok": True}

            mock_client = MagicMock()
            mock_client.request.return_value = mock_response
            mock_get_client.return_value = mock_client

            response = http_client.execute(request)

            # Should succeed
            assert response.status == 200
            assert response.body["ok"] is True

            # Verify files were passed
            call_args = mock_client.request.call_args
            assert "files" in call_args[1]
            assert call_args[1]["files"] is not None
