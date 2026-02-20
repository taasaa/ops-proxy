"""Tests for search command in HTTP client."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from ops_proxy.http_client import HTTPClient, Request
from ops_proxy.config import Config
from ops_proxy.rules import RulesEngine


class TestSearchCommand:
    """Tests for search command handling."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        config = Config(data_dir)
        return config

    @pytest.fixture
    def rules(self, config):
        """Create rules engine."""
        return RulesEngine(config)

    @pytest.fixture
    def http_client(self, config, rules):
        """Create HTTP client."""
        return HTTPClient(config, rules)

    def test_translate_search_command_missing_query(self, http_client):
        """Test search command without query returns None."""
        request = Request(
            id="search-1",
            method="GET",
            url="",
            headers={},
            body={
                "id": "search-1",
                "command": "search",
                "payload": {}  # Missing query
            },
            created_at=datetime.now(timezone.utc),
        )

        result = http_client._translate_unified_format(request)
        assert result is None

    def test_translate_search_command_success(self, http_client):
        """Test search command translates to Jina Search API (GET)."""
        import os
        # Set Jina API key via environment
        os.environ["TEST_JINA_KEY"] = "test_key_value"
        http_client.config._config["jina_api_key_env"] = "TEST_JINA_KEY"

        try:
            request = Request(
                id="search-1",
                method="GET",
                url="",
                headers={},
                body={
                    "id": "search-1",
                    "command": "search",
                    "payload": {"query": "What is quantum computing?"}
                },
                created_at=datetime.now(timezone.utc),
            )

            result = http_client._translate_unified_format(request)

            assert result is not None
            translated_request, files = result
            assert files is None
            assert translated_request.method == "GET"
            assert "s.jina.ai" in translated_request.url
            assert "q=" in translated_request.url
        finally:
            del os.environ["TEST_JINA_KEY"]

    def test_translate_search_command_no_api_key(self, http_client):
        """Test search command returns None when no API key."""
        # Ensure no API key
        if "TEST_JINA_KEY" in http_client.config._config:
            del http_client.config._config["jina_api_key_env"]

        request = Request(
            id="search-1",
            method="GET",
            url="",
            headers={},
            body={
                "id": "search-1",
                "command": "search",
                "payload": {"query": "test query"}
            },
            created_at=datetime.now(timezone.utc),
        )

        result = http_client._translate_unified_format(request)
        assert result is None


class TestSearchResponseSanitization:
    """Tests for search response sanitization."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        config = Config(data_dir)
        return config

    @pytest.fixture
    def rules(self, config):
        """Create rules engine."""
        return RulesEngine(config)

    @pytest.fixture
    def http_client(self, config, rules):
        """Create HTTP client."""
        return HTTPClient(config, rules)

    def test_sanitize_response_extracts_urls(self, http_client):
        """Test that search response extracts URLs."""
        # Jina search returns markdown with URLs
        content = """## 1. Quantum Computing
[1] URL Source: https://www.ibm.com/quantum

## 2. Quantum Wiki
[2] URL Source: https://en.wikipedia.org/wiki/Quantum"""

        result = http_client._sanitize_search_response(content)

        assert "https://www.ibm.com/quantum" in result["result"]["content"]
        assert "https://en.wikipedia.org/wiki/Quantum" in result["result"]["content"]
        assert result["result"]["type"] == "search"

    def test_sanitize_response_fallback_for_plain_text(self, http_client):
        """Test fallback for non-JSON response."""
        content = "Just plain content without URLs."

        result = http_client._sanitize_search_response(content)

        assert "Just plain content" in result["result"]["content"]

    def test_sanitize_response_type_is_search(self, http_client):
        """Test that response type is set to search."""
        content = "Some content"

        result = http_client._sanitize_search_response(content)

        assert result["result"]["type"] == "search"
        assert result["ok"] is True


class TestSearchConfig:
    """Tests for search configuration."""

    def test_jina_api_key_from_env(self, tmp_path):
        """Test Jina API key is loaded from environment."""
        import os
        os.environ["MY_JINA_KEY"] = "test_key_123"

        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        config = Config(data_dir)
        config._config["jina_api_key_env"] = "MY_JINA_KEY"

        assert config.jina_api_key == "test_key_123"

        del os.environ["MY_JINA_KEY"]

    def test_jina_api_key_not_set(self, tmp_path):
        """Test Jina API key returns None when not set."""
        import os
        # Ensure env var doesn't exist
        if "NONEXISTENT_JINA_KEY" in os.environ:
            del os.environ["NONEXISTENT_JINA_KEY"]

        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        config = Config(data_dir)
        config._config["jina_api_key_env"] = "NONEXISTENT_JINA_KEY"

        assert config.jina_api_key is None

    def test_max_search_content_length_default(self, tmp_path):
        """Test default max search content length."""
        config = Config(tmp_path / "data")

        assert config.max_search_content_length == 8192

    def test_max_search_content_length_custom(self, tmp_path):
        """Test custom max search content length."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        config = Config(data_dir)
        config._config["max_search_content_length"] = 4096

        assert config.max_search_content_length == 4096


class TestSearchExecution:
    """Tests for executing search requests."""

    @pytest.fixture
    def config_with_jina(self, tmp_path):
        """Create config with Jina API key."""
        import os
        os.environ["TEST_JINA_KEY"] = "test_key_123"

        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        config = Config(data_dir)
        config._config["jina_api_key_env"] = "TEST_JINA_KEY"

        # Add Jina URL to allowed URLs
        config._config["allowed_urls"] = [
            r"^https://api\.telegram\.org/",
            r"^https://r\.jina\.ai/",
        ]

        yield config

        del os.environ["TEST_JINA_KEY"]

    @pytest.fixture
    def rules(self, config_with_jina):
        """Create rules engine."""
        return RulesEngine(config_with_jina)

    @pytest.fixture
    def http_client(self, config_with_jina, rules):
        """Create HTTP client."""
        return HTTPClient(config_with_jina, rules)

    @patch("ops_proxy.http_client.httpx.Client")
    def test_execute_search_command(self, mock_client_class, http_client):
        """Test executing a search command."""
        # Mock response
        mock_response = MagicMock()
        mock_response.text = "# Quantum Computing\n\nContent about quantum computing."
        mock_response.headers = {}
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        request = Request(
            id="search-1",
            method="GET",
            url="",
            headers={},
            body={
                "id": "search-1",
                "command": "search",
                "payload": {"query": "quantum computing"}
            },
            created_at=datetime.now(timezone.utc),
        )

        response = http_client.execute(request)

        assert response.status == 200
        assert response.body is not None
        assert response.body["ok"] is True
        assert response.body["result"]["type"] == "search"
        assert "Quantum Computing" in response.body["result"]["content"]
