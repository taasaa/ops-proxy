"""OpenClaw hook notifier for immediate message delivery."""

import logging

import httpx

logger = logging.getLogger(__name__)


class OpenClawNotifier:
    """Notifies OpenClaw of new Telegram messages via hook."""

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

    def notify(self, message_text: str) -> bool:
        """Send notification to OpenClaw hook endpoint.

        Args:
            message_text: The text message from Telegram

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
            payload = {
                "text": message_text,
                "mode": "now",
            }

            response = client.post(self.hook_url, json=payload, headers=headers)
            response.raise_for_status()

            logger.info(f"Successfully notified OpenClaw: {message_text[:50]}...")
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


def notify_openclaw(hook_url: str | None, hook_token: str | None, message_text: str) -> bool:
    """Convenience function to send a notification to OpenClaw.

    Args:
        hook_url: The OpenClaw hook URL
        hook_token: The authentication token
        message_text: The message to send

    Returns:
        True if notification was sent successfully
    """
    notifier = OpenClawNotifier(hook_url, hook_token)
    try:
        return notifier.notify(message_text)
    finally:
        notifier.close()
