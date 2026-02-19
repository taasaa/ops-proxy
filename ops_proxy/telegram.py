"""Telegram long polling client for receiving messages."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)


class TelegramLongPoller:
    """Telegram bot long polling client."""

    def __init__(
        self,
        bot_token: str,
        messages_file: Path,
        timeout: int = 30,
        callback: Callable[[list[dict[str, Any]]], None] | None = None,
    ):
        self.bot_token = bot_token
        self.messages_file = messages_file
        self.timeout = timeout
        self.callback = callback
        self._offset: int = 0
        self._client: httpx.Client | None = None
        self._running = False

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout + 10)
        return self._client

    def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def _get_base_url(self) -> str:
        """Get Telegram API base URL."""
        return f"https://api.telegram.org/bot{self.bot_token}"

    def _load_offset(self) -> int:
        """Load last processed update_id from messages file."""
        try:
            if self.messages_file.exists():
                with open(self.messages_file) as f:
                    data = json.load(f)
                    # Store offset for next poll
                    updates = data.get("messages", [])
                    if updates:
                        return max(u.get("update_id", 0) for u in updates) + 1
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading offset: {e}")
        return 0

    def _save_messages(self, messages: list[dict[str, Any]]) -> None:
        """Save messages to new_messages.json."""
        try:
            # Ensure parent directory exists
            self.messages_file.parent.mkdir(parents=True, exist_ok=True)

            data = {"messages": messages}
            with open(self.messages_file, "w") as f:
                json.dump(data, f, indent=2, default=str)

            logger.info(f"Saved {len(messages)} messages to {self.messages_file}")
        except IOError as e:
            logger.error(f"Error saving messages: {e}")

    def poll(self) -> list[dict[str, Any]]:
        """Poll for new updates from Telegram."""
        try:
            client = self._get_client()
            url = f"{self._get_base_url()}/getUpdates"

            params = {
                "timeout": self.timeout,
                "offset": self._offset,
            }

            logger.debug(f"Polling Telegram (offset={self._offset})")
            response = client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            if not data.get("ok"):
                logger.error(f"Telegram API error: {data.get('description')}")
                return []

            updates = data.get("result", [])
            if not updates:
                return []

            # Extract messages from updates
            messages = []
            for update in updates:
                update_id = update.get("update_id", 0)
                message = update.get("message", {})
                if message:
                    message["update_id"] = update_id
                    messages.append(message)

                # Update offset to continue from this message
                if update_id >= self._offset:
                    self._offset = update_id + 1

            if messages:
                logger.info(f"Received {len(messages)} messages")
                self._save_messages(messages)

                # Call callback if provided
                if self.callback:
                    self.callback(messages)

            return messages

        except httpx.TimeoutException:
            # Normal - timeout means no new messages
            return []
        except httpx.HTTPError as e:
            logger.error(f"HTTP error during polling: {e}")
            return []
        except Exception as e:
            logger.error(f"Error during polling: {e}")
            return []

    def start(self, callback: Callable[[list[dict[str, Any]]], None] | None = None) -> None:
        """Start long polling loop."""
        if callback:
            self.callback = callback

        # Load offset from existing messages file
        self._offset = self._load_offset()
        logger.info(f"Starting long polling from offset {self._offset}")

        self._running = True

    def stop(self) -> None:
        """Stop long polling."""
        self._running = False
        logger.info("Stopped long polling")

    @property
    def running(self) -> bool:
        return self._running


def send_message(bot_token: str, chat_id: int | str, text: str) -> dict[str, Any] | None:
    """Send a message to a Telegram chat."""
    try:
        client = httpx.Client(timeout=30)
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        payload = {
            "chat_id": chat_id,
            "text": text,
        }

        response = client.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        if not data.get("ok"):
            logger.error(f"Failed to send message: {data.get('description')}")
            return None

        return data.get("result")
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return None
