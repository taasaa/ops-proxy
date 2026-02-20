"""Configuration loader for OpsProxy."""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


DEFAULT_DATA_DIR = Path.home() / ".openclaw-ops" / "ops-proxy"
DEFAULT_CONFIG_FILE = "config.yaml"
DEFAULT_REQUESTS_FILE = "requests.json"
DEFAULT_RESPONSES_FILE = "responses.json"
DEFAULT_INBOX_FILE = "inbox.json"
DEFAULT_LOG_FILE = "ops-proxy.log"
DEFAULT_PID_FILE = "ops-proxy.pid"
DEFAULT_LOCK_FILE = "ops-proxy.lock"


class Config:
    """OpsProxy configuration."""

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.config_file = self.data_dir / DEFAULT_CONFIG_FILE
        self.requests_file = self.data_dir / DEFAULT_REQUESTS_FILE
        self.responses_file = self.data_dir / DEFAULT_RESPONSES_FILE
        self.inbox_file = self.data_dir / DEFAULT_INBOX_FILE
        self.log_file = self.data_dir / DEFAULT_LOG_FILE
        self.pid_file = self.data_dir / DEFAULT_PID_FILE
        self.lock_file = self.data_dir / DEFAULT_LOCK_FILE

        # Load .env from data directory (project-scoped)
        env_file = self.data_dir / ".env"
        load_dotenv(env_file)

        self._config: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load configuration from YAML file."""
        if self.config_file.exists():
            with open(self.config_file) as f:
                self._config = yaml.safe_load(f) or {}
        else:
            self._config = self._default_config()
            self._save()

    def _save(self) -> None:
        """Save configuration to YAML file."""
        with open(self.config_file, "w") as f:
            yaml.safe_dump(self._config, f, default_flow_style=False)

    def _default_config(self) -> dict[str, Any]:
        """Return default configuration."""
        return {
            "version": "1.0",
            "token_env": "TG_BOT_TOKEN",
            "jina_api_key_env": "JINA_API_KEY",
            "hook_url": "http://127.0.0.1:18790/hook/agent",
            # Note: No URL allowlist - agent sends commands, not URLs
            # OpsProxy constructs all URLs internally
            "max_body_size": 1048576,
            "max_response_size": 1048576,
            "max_search_content_length": 8192,
            "request_timeout": 30,
            "log_level": "INFO",
        }

    @property
    def token_env(self) -> str:
        return self._config.get("token_env", "TG_BOT_TOKEN")

    @property
    def allowed_urls(self) -> list[str]:
        return self._config.get("allowed_urls", [])

    @property
    def max_body_size(self) -> int:
        return self._config.get("max_body_size", 1048576)

    @property
    def max_response_size(self) -> int:
        return self._config.get("max_response_size", 1048576)

    @property
    def request_timeout(self) -> int:
        return self._config.get("request_timeout", 30)

    @property
    def log_level(self) -> str:
        return self._config.get("log_level", "INFO")

    @property
    def hook_url(self) -> str | None:
        """Get OpenClaw hook URL from config or environment."""
        return self._config.get("hook_url") or os.environ.get("HOOK_URL")

    @property
    def hook_token(self) -> str | None:
        """Get OpenClaw hook token from config or environment."""
        return self._config.get("hook_token") or os.environ.get("HOOK_TOKEN")

    @property
    def bot_token(self) -> str | None:
        """Get bot token from environment variable."""
        return os.environ.get(self.token_env)

    @property
    def jina_api_key_env(self) -> str:
        return self._config.get("jina_api_key_env", "JINA_API_KEY")

    @property
    def jina_api_key(self) -> str | None:
        """Get Jina API key from environment variable."""
        return os.environ.get(self.jina_api_key_env)

    @property
    def max_search_content_length(self) -> int:
        return self._config.get("max_search_content_length", 8192)

    def reload(self) -> None:
        """Reload configuration from file."""
        self._load()
