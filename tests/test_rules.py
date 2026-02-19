"""Tests for URL validation rules."""

import pytest
from unittest.mock import MagicMock

from ops_proxy.rules import RulesEngine, ValidationResult
from ops_proxy.config import Config


class TestValidationResult:
    """Tests for ValidationResult named tuple."""

    def test_validation_result_allowed(self):
        """Test ValidationResult for allowed URL."""
        result = ValidationResult(True, "URL validated")
        assert result.allowed is True
        assert result.reason == "URL validated"

    def test_validation_result_blocked(self):
        """Test ValidationResult for blocked URL."""
        result = ValidationResult(False, "URL does not match allowed patterns")
        assert result.allowed is False
        assert result.reason == "URL does not match allowed patterns"


class TestRulesEngine:
    """Tests for RulesEngine."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create a test config."""
        config = Config(tmp_path / "data")
        config._config = {
            "allowed_urls": [
                r"^https://api\.telegram\.org/",
            ]
        }
        return config

    @pytest.fixture
    def rules(self, config):
        """Create a RulesEngine instance."""
        return RulesEngine(config)

    def test_validate_url_allowed(self, rules):
        """Test validating an allowed URL."""
        result = rules.validate_url("https://api.telegram.org/bot123:ABC/getMe")
        assert result.allowed is True
        assert result.reason == "URL validated"

    def test_validate_url_blocked(self, rules):
        """Test validating a blocked URL."""
        result = rules.validate_url("https://evil.com/malicious")
        assert result.allowed is False
        assert result.reason == "URL does not match allowed patterns"

    def test_validate_url_missing_scheme(self, rules):
        """Test validating URL with missing scheme."""
        result = rules.validate_url("api.telegram.org")
        assert result.allowed is False
        assert result.reason == "Missing URL scheme"

    def test_validate_url_invalid_scheme(self, rules):
        """Test validating URL with invalid scheme."""
        result = rules.validate_url("ftp://api.telegram.org")
        assert result.allowed is False
        assert result.reason == "Invalid scheme: ftp"

    def test_validate_url_invalid_url(self, rules):
        """Test validating an invalid URL."""
        result = rules.validate_url("not-a-valid-url")
        assert result.allowed is False
        assert "Invalid URL" in result.reason or "scheme" in result.reason.lower()

    def test_validate_url_with_query_params(self, rules):
        """Test validating URL with query parameters."""
        result = rules.validate_url("https://api.telegram.org/bot123:ABC/getUpdates?timeout=10")
        assert result.allowed is True

    def test_validate_url_https_required(self, rules):
        """Test that HTTP (non-SSL) is blocked."""
        result = rules.validate_url("http://api.telegram.org/bot123:ABC/getMe")
        assert result.allowed is False


class TestRulesEngineMultiplePatterns:
    """Tests for RulesEngine with multiple URL patterns."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create a test config with multiple patterns."""
        config = Config(tmp_path / "data")
        config._config = {
            "allowed_urls": [
                r"^https://api\.telegram\.org/",
                r"^https://example\.com/api/",
            ]
        }
        return config

    @pytest.fixture
    def rules(self, config):
        """Create a RulesEngine instance."""
        return RulesEngine(config)

    def test_validate_url_first_pattern(self, rules):
        """Test URL matching first pattern."""
        result = rules.validate_url("https://api.telegram.org/bot123:ABC/getMe")
        assert result.allowed is True

    def test_validate_url_second_pattern(self, rules):
        """Test URL matching second pattern."""
        result = rules.validate_url("https://example.com/api/users")
        assert result.allowed is True

    def test_validate_url_no_pattern_match(self, rules):
        """Test URL matching no pattern."""
        result = rules.validate_url("https://other.com/api")
        assert result.allowed is False


class TestRulesEngineReload:
    """Tests for RulesEngine reload functionality."""

    def test_reload_patterns(self, tmp_path):
        """Test reloading patterns from config."""
        config = Config(tmp_path / "data")
        config._config = {
            "allowed_urls": [
                r"^https://api\.telegram\.org/",
            ]
        }
        rules = RulesEngine(config)

        # Initial validation
        result = rules.validate_url("https://api.telegram.org/test")
        assert result.allowed is True

        # Update config with new pattern
        config._config = {
            "allowed_urls": [
                r"^https://new\.pattern\.com/",
            ]
        }
        rules.reload()

        # Old URL should now be blocked
        result = rules.validate_url("https://api.telegram.org/test")
        assert result.allowed is False

        # New URL should be allowed
        result = rules.validate_url("https://new.pattern.com/test")
        assert result.allowed is True
