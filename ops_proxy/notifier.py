"""OpenClaw hook notifier for waking agent with new messages."""

import logging

import httpx

logger = logging.getLogger(__name__)


class OpenClawNotifier:
    """Notifies OpenClaw of new Telegram messages via /hook/wake endpoint."""

    def __init__(self, hook_url: str | None, hook_token: str | None):
        self.hook_url = hook_url
        self.hook_token = hook_token
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=10)
        return self._client

    def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def notify_inbox(self, update_id: int, chat_id: int | str, text: str) -> bool:
        """Send wake notification to OpenClaw about new inbox message.

        Uses /hook/wake - tells the agent to read from inbox file.
        Does NOT deliver - the agent writes HTTP requests to requests.json for OpsProxy to execute.

        Args:
            update_id: The Telegram update_id
            chat_id: The Telegram chat ID
            text: The message text

        Returns:
            True if notification was sent successfully, False otherwise
        """
        if not self.hook_url:
            logger.warning("Hook URL not configured, skipping notification")
            return False

        if not self.hook_token:
            logger.warning("Hook token not configured, skipping notification")
            return False

        try:
            client = self._get_client()
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.hook_token}",
            }

            # Use /hook/wake - tell agent to read from inbox
            wake_url = self.hook_url.replace("/agent", "/wake")

            # Tell the agent to go read from inbox - no mention of Telegram
            inbox_msg = f"New message in inbox: read from ~/.openclaw-ops/ops-proxy/inbox.json with update_id={update_id}"

            payload = {
                "text": inbox_msg,
                "mode": "now",
            }

            response = client.post(wake_url, json=payload, headers=headers)
            response.raise_for_status()

            logger.info(f"Successfully woke OpenClaw: inbox update_id={update_id}")
            return True

        except httpx.TimeoutException:
            logger.error("Timeout notifying OpenClaw")
            return False
        except httpx.HTTPError as e:
            logger.error(f"HTTP error notifying OpenClaw: {e}")
            return False
        except Exception as e:
            logger.error(f"Error notifying OpenClaw: {e}")
            return False

    def is_configured(self) -> bool:
        """Check if notifier is properly configured."""
        return bool(self.hook_url and self.hook_token)


def notify_openclaw(hook_url: str | None, hook_token: str | None, message_text: str, chat_id: int | str | None = None) -> bool:
    """Convenience function to send a wake notification to OpenClaw.

    Args:
        hook_url: The OpenClaw hook URL
        hook_token: The authentication token
        message_text: The message to send
        chat_id: The Telegram chat ID (unused)

    Returns:
        True if notification was sent successfully
    """
    notifier = OpenClawNotifier(hook_url, hook_token)
    try:
        # Extract update_id from message_text if available (format: "update_id=123")
        update_id = None
        if message_text and "update_id=" in message_text:
            try:
                update_id = int(message_text.split("update_id=")[1].split()[0])
            except (ValueError, IndexError):
                pass
        # If we have a chat_id in the expected format, use it
        if chat_id is None:
            chat_id = 0
        return notifier.notify_inbox(update_id or 0, chat_id, message_text or "")
    finally:
        notifier.close()
