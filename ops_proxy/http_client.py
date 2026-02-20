"""HTTP client for executing validated requests."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from ops_proxy.config import Config
from ops_proxy.rules import RulesEngine, ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class Request:
    """A pending HTTP request."""
    id: str
    method: str
    url: str
    headers: dict[str, str]
    body: dict[str, Any] | None
    created_at: datetime
    status: str = "pending"


@dataclass
class Response:
    """Response from HTTP request."""
    status: int | None
    body: dict[str, Any] | None
    received_at: datetime
    error: str | None


class HTTPClient:
    """HTTP client for executing validated requests."""

    def __init__(self, config: Config, rules: RulesEngine):
        self.config = config
        self.rules = rules
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(self.config.request_timeout),
                follow_redirects=False,  # Security: don't follow redirects automatically
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5,
                ),
            )
        return self._client

    def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def _translate_unified_format(self, request: Request) -> tuple[Request, dict | None] | None:
        """Translate unified command format to Telegram API call.

        Agent writes:
            {
              "id": "req-1",
              "command": "send",
              "payload": {
                "chat_id": "...",
                "text": "Hello world",      // optional
                "path": "/path/to/file",    // optional
                "format": "markdown"       // optional: markdown | html | plain
              }
            }

        At least one of text or path is required.

        Returns (request, files) tuple, or None if not a unified format request.
        """
        if not request.body or not isinstance(request.body, dict):
            return None

        # Check for unified format: has command and payload
        command = request.body.get("command")
        payload = request.body.get("payload")

        if command != "send" or not payload or not isinstance(payload, dict):
            return None

        chat_id = payload.get("chat_id")
        text = payload.get("text")
        file_path = payload.get("path")
        format_type = payload.get("format", "plain")

        # At least one of text or path required
        if not chat_id or (not text and not file_path):
            logger.warning(f"Request {request.id} missing chat_id, text, or path in unified format")
            return None

        # Get bot token
        token = self.config.bot_token
        if not token:
            logger.warning(f"Request {request.id} no bot token configured")
            return None

        files = None

        # Handle file upload
        if file_path:
            from pathlib import Path
            path = Path(file_path).expanduser().resolve()

            if not path.exists():
                logger.warning(f"Request {request.id}: file not found: {path}")
                return None

            try:
                file_content = path.read_bytes()
            except IOError as e:
                logger.warning(f"Request {request.id}: cannot read file {path}: {e}")
                return None

            logger.info(f"Translating request {request.id} to Telegram sendDocument: {path.name} to {chat_id}")

            # Build body for document
            body = {"chat_id": str(chat_id)}
            if text:
                body["caption"] = str(text)
            if format_type != "plain":
                body["parse_mode"] = format_type.capitalize()

            files = {"document": (path.name, file_content)}

            return (
                Request(
                    id=request.id,
                    method="POST",
                    url=f"https://api.telegram.org/bot{token}/sendDocument",
                    headers={},
                    body=body,
                    created_at=request.created_at,
                    status="pending",
                ),
                files,
            )

        # Handle text message
        logger.info(f"Translating request {request.id} to Telegram sendMessage: {chat_id}")

        body = {"chat_id": str(chat_id), "text": str(text)}
        if format_type != "plain":
            body["parse_mode"] = format_type.capitalize()

        return (
            Request(
                id=request.id,
                method="POST",
                url=f"https://api.telegram.org/bot{token}/sendMessage",
                headers={"Content-Type": "application/json"},
                body=body,
                created_at=request.created_at,
                status="pending",
            ),
            None,
        )

    def execute(self, request: Request) -> Response:
        """Execute an HTTP request after validation."""

        files = None

        # Check for unified format (command + payload)
        unified = self._translate_unified_format(request)
        if unified:
            request, files = unified

        # Validate URL
        validation = self.rules.validate_url(request.url)
        if not validation.allowed:
            logger.warning(f"Request {request.id} blocked: {validation.reason}")
            return Response(
                status=None,
                body=None,
                received_at=datetime.now(timezone.utc),
                error=validation.reason,
            )

        # Inject bot token if URL contains placeholder
        url = request.url
        token = self.config.bot_token
        if token and "<token>" in url:
            url = url.replace("<token>", token)

        # Check body size
        if request.body:
            import json
            body_size = len(json.dumps(request.body).encode())
            max_size = self.config.max_body_size
            if body_size > max_size:
                logger.warning(f"Request {request.id} blocked: body too large ({body_size} bytes)")
                return Response(
                    status=None,
                    body=None,
                    received_at=datetime.now(timezone.utc),
                    error=f"Body size {body_size} exceeds limit {max_size}",
                )

        try:
            logger.info(f"Executing request {request.id}: {request.method} {url}")
            client = self._get_client()

            # Handle multipart file upload for documents
            if files:
                response = client.request(
                    method=request.method,
                    url=url,
                    files=files,
                    data=request.body,
                )
            else:
                response = client.request(
                    method=request.method,
                    url=url,
                    headers=request.headers,
                    json=request.body,
                )

            # Check response size
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > self.config.max_response_size:
                logger.warning(f"Response {request.id} too large: {content_length} bytes")
                return Response(
                    status=response.status_code,
                    body=None,
                    received_at=datetime.now(timezone.utc),
                    error=f"Response size {content_length} exceeds limit {self.config.max_response_size}",
                )

            logger.info(f"Response {request.id}: {response.status_code}")
            return Response(
                status=response.status_code,
                body=response.json() if response.text else None,
                received_at=datetime.now(timezone.utc),
                error=None,
            )

        except httpx.TimeoutException as e:
            logger.error(f"Request {request.id} timed out: {e}")
            return Response(
                status=None,
                body=None,
                received_at=datetime.now(timezone.utc),
                error=f"Timeout: {e}",
            )
        except httpx.HTTPError as e:
            logger.error(f"Request {request.id} failed: {e}")
            return Response(
                status=None,
                body=None,
                received_at=datetime.now(timezone.utc),
                error=f"HTTP error: {e}",
            )
        except Exception as e:
            logger.error(f"Request {request.id} failed: {e}")
            return Response(
                status=None,
                body=None,
                received_at=datetime.now(timezone.utc),
                error=str(e),
            )
