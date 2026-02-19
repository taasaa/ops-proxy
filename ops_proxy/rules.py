"""Rules engine for URL validation."""

import logging
import re
from typing import NamedTuple
from urllib.parse import urlparse

from ops_proxy.config import Config


logger = logging.getLogger(__name__)


class ValidationResult(NamedTuple):
    """Result of URL validation."""
    allowed: bool
    reason: str


class RulesEngine:
    """Rules engine for validating requests."""

    def __init__(self, config: Config):
        self.config = config
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns."""
        self._compiled_patterns = []
        for pattern in self.config.allowed_urls:
            try:
                self._compiled_patterns.append(re.compile(pattern))
            except re.error as e:
                logger.error(f"Invalid regex pattern: {pattern}: {e}")

    def validate_url(self, url: str) -> ValidationResult:
        """Validate URL against allowed patterns."""
        try:
            parsed = urlparse(url)
        except Exception as e:
            return ValidationResult(False, f"Invalid URL: {e}")

        if not parsed.scheme:
            return ValidationResult(False, "Missing URL scheme")

        if parsed.scheme not in ("http", "https"):
            return ValidationResult(False, f"Invalid scheme: {parsed.scheme}")

        # Check URL pattern
        for pattern in self._compiled_patterns:
            if pattern.match(url):
                return ValidationResult(True, "URL validated")

        return ValidationResult(False, "URL does not match allowed patterns")

    def reload(self) -> None:
        """Reload rules from config."""
        self._compile_patterns()
