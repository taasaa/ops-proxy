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
