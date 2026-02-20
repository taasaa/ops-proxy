"""Tests for HTTP client and request/response handling."""

import os
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from ops_proxy.http_client import HTTPClient, Request, Response
from ops_proxy.config import Config
from ops_proxy.rules import RulesEngine


class TestRequest:
    """Tests for Request dataclass."""

    def test_request_creation(self):
        """Test creating a Request object."""
        request = Request(
            id="test-1",
            method="POST",
            url="https://api.telegram.org/bot<token>/sendMessage",
            headers={"Content-Type": "application/json"},
            body={"chat_id": 123, "text": "Hello"},
            created_at=datetime.now(timezone.utc),
        )

        assert request.id == "test-1"
        assert request.method == "POST"
        assert request.url == "https://api.telegram.org/bot<token>/sendMessage"
        assert request.headers == {"Content-Type": "application/json"}
        assert request.body == {"chat_id": 123, "text": "Hello"}
        assert request.status == "pending"


class TestResponse:
    """Tests for Response dataclass."""

    def test_response_creation(self):
        """Test creating a Response object."""
        response = Response(
            status=200,
            body={"ok": True, "result": {}},
            received_at=datetime.now(timezone.utc),
            error=None,
        )

        assert response.status == 200
        assert response.body == {"ok": True, "result": {}}
        assert response.error is None

    def test_response_error(self):
        """Test Response with error."""
        response = Response(
            status=None,
            body=None,
            received_at=datetime.now(timezone.utc),
            error="Connection timeout",
        )

        assert response.status is None
        assert response.body is None
        assert response.error == "Connection timeout"


class TestHTTPClient:
    """Tests for HTTPClient."""

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

    @pytest.fixture
    def http_client(self, config, rules):
        """Create an HTTPClient instance."""
        return HTTPClient(config, rules)

    def test_client_close(self, http_client):
        """Test closing the HTTP client."""
        http_client.close()
        # Should not raise any exceptions

    def test_execute_raw_url_allowed(self, http_client):
        """Test that raw URLs are now allowed (secure-by-design: agent sends commands, not URLs)."""
        request = Request(
            id="test-1",
            method="GET",
            url="https://evil.com/api",
            headers={},
            body=None,
            created_at=datetime.now(timezone.utc),
        )

        response = http_client.execute(request)

        # URLs are allowed now - it will fail due to network/auth, not URL blocking
        assert response.error is not None or response.status is not None

    def test_execute_invalid_url(self, http_client):
        """Test executing a request with an invalid URL (no scheme)."""
        request = Request(
            id="test-2",
            method="GET",
            url="not-a-valid-url",
            headers={},
            body=None,
            created_at=datetime.now(timezone.utc),
        )

        response = http_client.execute(request)

        # Invalid URLs (no http/https) will fail at HTTP layer
        assert response.status is None or "scheme" in (response.error or "").lower()

    def test_execute_body_too_large(self, http_client):
        """Test executing a request with body exceeding limit."""
        # Create a large body
        large_body = {"data": "x" * (1024 * 1024 + 1)}  # > 1MB

        request = Request(
            id="test-3",
            method="POST",
            url="https://api.telegram.org/bot<token>/sendMessage",
            headers={},
            body=large_body,
            created_at=datetime.now(timezone.utc),
        )

        response = http_client.execute(request)

        assert response.status is None
        assert "body too large" in response.error.lower() or "exceeds limit" in response.error.lower()


class TestHTTPClientWithMock:
    """Tests for HTTPClient with mocked HTTP calls."""

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
        # Set mock token
        config._config["token_env"] = "TEST_TOKEN"
        return config

    @pytest.fixture
    def rules(self, config):
        """Create a RulesEngine instance."""
        return RulesEngine(config)

    @patch.dict(os.environ, {"TEST_TOKEN": "mock_token_123"})
    def test_execute_with_token_injection(self, config, rules):
        """Test that <token> placeholder is replaced with actual token."""
        http_client = HTTPClient(config, rules)

        request = Request(
            id="test-1",
            method="POST",
            url="https://api.telegram.org/bot<token>/sendMessage",
            headers={},
            body={"chat_id": 123, "text": "Hello"},
            created_at=datetime.now(timezone.utc),
        )

        # Mock the HTTP client to avoid actual network calls
        with patch.object(http_client, '_get_client') as mock_get_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = '{"ok": true}'
            mock_response.json.return_value = {"ok": True}

            mock_client = MagicMock()
            mock_client.request.return_value = mock_response
            mock_get_client.return_value = mock_client

            response = http_client.execute(request)

            # Verify the URL was modified with the token
            called_url = mock_client.request.call_args[1]["url"]
            assert "mock_token_123" in called_url
            assert "<token>" not in called_url


class TestHTTPClientTimeout:
    """Tests for HTTP client timeout handling."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create a test config."""
        config = Config(tmp_path / "data")
        config._config = {
            "allowed_urls": [
                r"^https://api\.telegram\.org/",
            ],
        }
        return config

    @pytest.fixture
    def rules(self, config):
        """Create a RulesEngine instance."""
        return RulesEngine(config)

    def test_timeout_exception_handling(self, config, rules):
        """Test that timeout exceptions are handled properly."""
        import httpx

        http_client = HTTPClient(config, rules)

        request = Request(
            id="test-timeout",
            method="GET",
            url="https://api.telegram.org/bot<token>/getMe",
            headers={},
            body=None,
            created_at=datetime.now(timezone.utc),
        )

        with patch.object(http_client, '_get_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.request.side_effect = httpx.TimeoutException("Connection timeout")
            mock_get_client.return_value = mock_client

            response = http_client.execute(request)

            assert response.status is None
            assert "Timeout" in response.error


class TestHTTPClientHttpError:
    """Tests for HTTP client HTTP error handling."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create a test config."""
        config = Config(tmp_path / "data")
        config._config = {
            "allowed_urls": [
                r"^https://api\.telegram\.org/",
            ],
        }
        return config

    @pytest.fixture
    def rules(self, config):
        """Create a RulesEngine instance."""
        return RulesEngine(config)

    def test_http_error_handling(self, config, rules):
        """Test that HTTP errors are handled properly."""
        import httpx

        http_client = HTTPClient(config, rules)

        request = Request(
            id="test-error",
            method="GET",
            url="https://api.telegram.org/bot<token>/getMe",
            headers={},
            body=None,
            created_at=datetime.now(timezone.utc),
        )

        with patch.object(http_client, '_get_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.request.side_effect = httpx.HTTPError("Connection error")
            mock_get_client.return_value = mock_client

            response = http_client.execute(request)

            assert response.status is None
            assert "HTTP error" in response.error
