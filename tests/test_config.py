"""Tests for configuration loading."""

import os
import pytest
import tempfile
from pathlib import Path

from ops_proxy.config import Config


class TestConfig:
    """Tests for Config class."""

    def test_default_config_creation(self, tmp_path):
        """Test that default config is created if no config file exists."""
        data_dir = tmp_path / "data"
        config = Config(data_dir)

        assert config.data_dir == data_dir
        assert config.config_file == data_dir / "config.yaml"
        assert config.requests_file == data_dir / "requests.json"
        assert config.responses_file == data_dir / "responses.json"

    def test_default_config_values(self, tmp_path):
        """Test default configuration values."""
        config = Config(tmp_path / "data")

        assert config.token_env == "TG_BOT_TOKEN"
        assert config.max_body_size == 1048576
        assert config.request_timeout == 30
        assert config.log_level == "INFO"
        # Check that api.telegram.org is in the default allowed_urls pattern
        assert len(config.allowed_urls) == 1
        assert "api" in config.allowed_urls[0] and "telegram" in config.allowed_urls[0]

    def test_custom_config_values(self, tmp_path):
        """Test loading custom configuration values."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        config_file = data_dir / "config.yaml"

        # Write custom config
        import yaml
        custom_config = {
            "token_env": "MY_TOKEN",
            "allowed_urls": [
                r"^https://custom\.api\.com/",
            ],
            "max_body_size": 2097152,
            "request_timeout": 60,
            "log_level": "DEBUG",
        }
        with open(config_file, "w") as f:
            yaml.safe_dump(custom_config, f)

        config = Config(tmp_path / "data")

        assert config.token_env == "MY_TOKEN"
        assert config.max_body_size == 2097152
        assert config.request_timeout == 60
        assert config.log_level == "DEBUG"
        assert config.allowed_urls == [r"^https://custom\.api\.com/"]

    def test_config_data_dir_creation(self, tmp_path):
        """Test that data directory is created."""
        data_dir = tmp_path / "new" / "nested" / "dir"
        config = Config(data_dir)

        assert data_dir.exists()
        assert data_dir.is_dir()

    def test_bot_token_from_env(self, tmp_path):
        """Test getting bot token from environment variable."""
        os.environ["TEST_TOKEN_VAR"] = "my_test_token"

        config = Config(tmp_path / "data")
        config._config = {"token_env": "TEST_TOKEN_VAR"}

        assert config.bot_token == "my_test_token"

        del os.environ["TEST_TOKEN_VAR"]

    def test_bot_token_not_set(self, tmp_path):
        """Test bot token when environment variable is not set."""
        # Make sure the env var doesn't exist
        if "NONEXISTENT_TOKEN_VAR" in os.environ:
            del os.environ["NONEXISTENT_TOKEN_VAR"]

        config = Config(tmp_path / "data")
        config._config = {"token_env": "NONEXISTENT_TOKEN_VAR"}

        assert config.bot_token is None


class TestConfigReload:
    """Tests for configuration reload."""

    def test_reload_config(self, tmp_path):
        """Test reloading configuration from file."""
        import yaml

        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        config_file = data_dir / "config.yaml"

        # Write initial config
        initial_config = {
            "log_level": "INFO",
        }
        with open(config_file, "w") as f:
            yaml.safe_dump(initial_config, f)

        config = Config(tmp_path / "data")
        assert config.log_level == "INFO"

        # Update config file
        updated_config = {
            "log_level": "DEBUG",
        }
        with open(config_file, "w") as f:
            yaml.safe_dump(updated_config, f)

        # Reload
        config.reload()
        assert config.log_level == "DEBUG"


class TestConfigFiles:
    """Tests for configuration file paths."""

    def test_default_file_paths(self, tmp_path):
        """Test default file paths."""
        config = Config(tmp_path / "data")

        assert config.config_file.name == "config.yaml"
        assert config.requests_file.name == "requests.json"
        assert config.responses_file.name == "responses.json"
        assert config.log_file.name == "ops-proxy.log"
        assert config.pid_file.name == "ops-proxy.pid"
        assert config.lock_file.name == "ops-proxy.lock"
        assert config.inbox_file.name == "inbox.json"


class TestConfigHookSettings:
    """Tests for hook URL and token configuration."""

    def test_hook_url_from_config(self, tmp_path):
        """Test getting hook URL from config file."""
        import yaml

        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        config_file = data_dir / "config.yaml"

        config_data = {
            "hook_url": "http://localhost:18790/hook/agent",
            "hook_token": "secret_token_123",
        }
        with open(config_file, "w") as f:
            yaml.safe_dump(config_data, f)

        config = Config(tmp_path / "data")

        assert config.hook_url == "http://localhost:18790/hook/agent"
        assert config.hook_token == "secret_token_123"

    def test_hook_url_from_env(self, tmp_path):
        """Test getting hook URL from environment variable."""
        import yaml

        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        config_file = data_dir / "config.yaml"

        # Write minimal config (no hook settings)
        with open(config_file, "w") as f:
            yaml.safe_dump({}, f)

        # Set environment variables
        os.environ["HOOK_URL"] = "http://custom:9999/hook/agent"
        os.environ["HOOK_TOKEN"] = "env_token"

        try:
            config = Config(tmp_path / "data")

            # Environment should override
            assert config.hook_url == "http://custom:9999/hook/agent"
            assert config.hook_token == "env_token"
        finally:
            del os.environ["HOOK_URL"]
            del os.environ["HOOK_TOKEN"]

    def test_hook_url_none_when_not_configured(self, tmp_path):
        """Test hook_url returns None when not configured."""
        import yaml

        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        config_file = data_dir / "config.yaml"

        # Make sure env vars are not set
        if "HOOK_URL" in os.environ:
            del os.environ["HOOK_URL"]
        if "HOOK_TOKEN" in os.environ:
            del os.environ["HOOK_TOKEN"]

        with open(config_file, "w") as f:
            yaml.safe_dump({}, f)

        config = Config(tmp_path / "data")

        assert config.hook_url is None
        assert config.hook_token is None


class TestConfigMaxResponseSize:
    """Tests for max_response_size configuration."""

    def test_default_max_response_size(self, tmp_path):
        """Test default max_response_size value."""
        config = Config(tmp_path / "data")

        assert config.max_response_size == 1048576

    def test_custom_max_response_size(self, tmp_path):
        """Test custom max_response_size value."""
        import yaml

        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        config_file = data_dir / "config.yaml"

        config_data = {
            "max_response_size": 2097152,
        }
        with open(config_file, "w") as f:
            yaml.safe_dump(config_data, f)

        config = Config(tmp_path / "data")

        assert config.max_response_size == 2097152
