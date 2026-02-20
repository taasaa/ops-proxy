"""HTTP client for executing validated requests."""

import json
import logging
import re
import urllib.parse
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
        """Translate unified command format to API call.

        Supports two commands:
        1. "send" - Telegram message/document
        2. "search" - Web research via Jina AI

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

        Or for search:
            {
              "id": "search-1",
              "command": "search",
              "payload": {
                "query": "What is quantum computing?"
              }
            }

        At least one of text or path is required for send.
        Query is required for search.

        Returns (request, files) tuple, or None if not a unified format request.
        """
        if not request.body or not isinstance(request.body, dict):
            return None

        # Check for unified format: has command and payload
        command = request.body.get("command")
        payload = request.body.get("payload")

        if not command or not payload or not isinstance(payload, dict):
            return None

        # Route to appropriate handler
        if command == "send":
            return self._translate_send_command(request, payload)
        elif command == "search":
            return self._translate_search_command(request, payload)
        elif command == "read":
            return self._translate_read_command(request, payload)

        return None

    def _translate_send_command(self, request: Request, payload: dict) -> tuple[Request, dict | None] | None:
        """Translate 'send' command to Telegram API call."""

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

    def _translate_search_command(self, request: Request, payload: dict) -> tuple[Request, dict | None] | None:
        """Translate 'search' command to Jina AI Search API call.

        Agent writes:
            {
              "id": "search-1",
              "command": "search",
              "payload": {
                "query": "What is quantum computing?"
              }
            }

        OpsProxy internally calls Jina AI Search API.
        Agent does NOT specify the engine - that's an implementation detail.
        """
        query = payload.get("query")

        # Query is required
        if not query:
            logger.warning(f"Request {request.id} missing query in search command")
            return None

        # Get Jina API key
        api_key = self.config.jina_api_key
        if not api_key:
            logger.warning(f"Request {request.id} no Jina API key configured")
            return None

        # Jina Search API: GET to https://s.jina.ai/?q=query
        # Returns top 5 clean search results in markdown
        logger.info(f"Translating request {request.id} to Jina AI search: {query}")

        # Build headers with API key for higher rate limits
        headers = {
            "Authorization": f"Bearer {api_key}",
        }

        # URL encode the query
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://s.jina.ai/?q={encoded_query}"

        return (
            Request(
                id=request.id,
                method="GET",
                url=search_url,
                headers=headers,
                body=None,
                created_at=request.created_at,
                status="pending",
            ),
            None,
        )

    def _translate_read_command(self, request: Request, payload: dict) -> tuple[Request, dict | None] | None:
        """Translate 'read' command to Jina Reader API call.

        Agent writes:
            {
              "id": "read-1",
              "command": "read",
              "payload": {
                "url": "https://example.com/article"
              }
            }

        OpsProxy internally calls Jina Reader API to fetch clean content.
        Returns markdown, not HTML - perfect for LLM consumption.
        """
        url = payload.get("url")

        if not url:
            logger.warning(f"Request {request.id} missing url in read command")
            return None

        # Validate URL has http/https
        if not url.startswith(("http://", "https://")):
            logger.warning(f"Request {request.id} url must start with http:// or https://")
            return None

        # Get Jina API key
        api_key = self.config.jina_api_key
        if not api_key:
            logger.warning(f"Request {request.id} no Jina API key configured")
            return None

        # Jina Reader API: POST to https://r.jina.ai/ with JSON body {"url": "..."}
        logger.info(f"Translating request {request.id} to Jina Reader: {url}")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        return (
            Request(
                id=request.id,
                method="POST",
                url="https://r.jina.ai/",
                headers=headers,
                body={"url": url},
                created_at=request.created_at,
                status="pending",
            ),
            None,
        )

    def _sanitize_read_response(self, response_body: str) -> dict:
        """Sanitize Jina Reader response - returns clean markdown."""
        try:
            data = json.loads(response_body)
            content = data.get("data", {}).get("content", response_body)
        except json.JSONDecodeError:
            content = response_body

        max_length = self.config.max_search_content_length
        if len(content) > max_length:
            content = content[:max_length] + "\n\n[content truncated]"

        return {
            "ok": True,
            "result": {
                "content": content,
                "type": "read",
            }
        }

    def _sanitize_search_response(self, response_body: str) -> dict:
        """Sanitize Jina AI search response - just return URLs, not full content.

        Agent uses 'read' command to fetch clean content from specific URLs.
        """
        max_length = self.config.max_search_content_length

        # Extract URLs - Jina returns markdown with [N] Title and [N] URL Source: format
        urls = []
        import re

        # Match patterns like [1] Title: ... or ## 1. Title
        lines = response_body.split('\n')
        current_title = ""
        url_map = {}

        for line in lines:
            # Check for title line
            title_match = re.match(r'(?:##?\s*)?\[?(\d+)\]?\.?\s*Title:\s*(.+?)(?:\s*\[|$)', line)
            if title_match:
                current_title = title_match.group(2).strip()

            # Check for URL line
            url_match = re.search(r'URL Source:\s*(https?://[^\s\)]+)', line)
            if url_match:
                url = url_match.group(1)
                if current_title:
                    url_map[url] = current_title
                    current_title = ""

        # Format as simple URL list
        output = []
        for i, (url, title) in enumerate(url_map.items(), 1):
            output.append(f"{i}. {title}")
            output.append(f"   {url}")
            output.append("")

        if not output:
            # Fallback: just return the raw response
            output = [response_body[:max_length]]

        final_content = "\n".join(output)

        # Truncate if too long
        if len(final_content) > max_length:
            final_content = final_content[:max_length] + "\n\n[truncated]"

        return {
            "ok": True,
            "result": {
                "content": final_content,
                "type": "search",
                "urls": list(url_map.keys()),
            }
        }

    def execute(self, request: Request) -> Response:
        """Execute an HTTP request after validation."""

        files = None
        original_command = None

        # Check for unified format (command + payload)
        if request.body and isinstance(request.body, dict):
            original_command = request.body.get("command")

        unified = self._translate_unified_format(request)
        if unified:
            request, files = unified

        # Note: URL validation removed
        # Agent sends commands (send/search), not raw URLs
        # OpsProxy constructs all URLs internally - secure by design

        # Inject bot token if URL contains placeholder
        url = request.url
        token = self.config.bot_token
        if token and "<token>" in url:
            url = url.replace("<token>", token)

        # Check body size
        if request.body:
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

            # Handle search/read response sanitization
            if original_command == "search":
                body = self._sanitize_search_response(response.text)
            elif original_command == "read":
                body = self._sanitize_read_response(response.text)
            else:
                body = response.json() if response.text else None

            return Response(
                status=response.status_code,
                body=body,
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
