"""OpsProxy CLI - Main daemon entry point."""

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from ops_proxy import __version__
from ops_proxy.config import Config
from ops_proxy.http_client import HTTPClient, Request, Response
from ops_proxy.rules import RulesEngine
from ops_proxy.telegram import TelegramLongPoller
from ops_proxy.watcher import FileWatcher


logger = logging.getLogger(__name__)


class OpsProxyDaemon:
    """OpsProxy daemon for processing HTTP requests."""

    def __init__(self, data_dir: Path | None = None):
        self.config = Config(data_dir)
        self.rules = RulesEngine(self.config)
        self.http_client = HTTPClient(self.config, self.rules)
        self.watcher: FileWatcher | None = None
        self.poller: TelegramLongPoller | None = None
        self._running = False

    def _setup_logging(self) -> None:
        """Configure logging."""
        log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(self.config.log_file),
                logging.StreamHandler(sys.stdout),
            ],
        )

    def _load_requests(self) -> list[dict]:
        """Load pending requests from requests.json."""
        try:
            if not self.config.requests_file.exists():
                return []
            with open(self.config.requests_file) as f:
                data = json.load(f)
            return [r for r in data.get("requests", []) if r.get("status") == "pending"]
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading requests: {e}")
            return []

    def _save_responses(self, responses: dict) -> None:
        """Save responses to responses.json."""
        try:
            # Load existing responses
            existing = {}
            if self.config.responses_file.exists():
                with open(self.config.responses_file) as f:
                    existing = json.load(f)

            # Merge responses
            if "responses" not in existing:
                existing["responses"] = {}
            existing["responses"].update(responses)

            # Save
            with open(self.config.responses_file, "w") as f:
                json.dump(existing, f, indent=2, default=str)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error saving responses: {e}")

    def _update_request_status(self, request_id: str, status: str) -> None:
        """Update request status in requests.json."""
        try:
            if not self.config.requests_file.exists():
                return
            with open(self.config.requests_file) as f:
                data = json.load(f)

            for req in data.get("requests", []):
                if req.get("id") == request_id:
                    req["status"] = status
                    break

            with open(self.config.requests_file, "w") as f:
                json.dump(data, f, indent=2)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error updating request status: {e}")

    def _process_requests(self, requests: list[dict]) -> None:
        """Process a list of requests."""
        responses = {}

        for req in requests:
            request_id = req.get("id")
            if not request_id:
                continue

            logger.info(f"Processing request {request_id}")

            # Parse request
            http_request = Request(
                id=request_id,
                method=req.get("method", "POST"),
                url=req.get("url", ""),
                headers=req.get("headers", {}),
                body=req.get("body"),
                created_at=datetime.now(timezone.utc),
                status="pending",
            )

            # Execute request
            response = self.http_client.execute(http_request)

            # Build response dict
            responses[request_id] = {
                "status": response.status,
                "body": response.body,
                "received_at": response.received_at.isoformat(),
                "error": response.error,
            }

            # Update request status
            self._update_request_status(
                request_id, "completed" if response.error is None else "failed"
            )

        # Save all responses
        if responses:
            self._save_responses(responses)

    def _handle_file_change(self, requests: list[dict]) -> None:
        """Handle file change event."""
        if not requests:
            return
        self._process_requests(requests)

    def start(self) -> None:
        """Start the daemon."""
        self._setup_logging()
        logger.info(f"Starting OpsProxy daemon v{__version__}")
        logger.info(f"Data directory: {self.config.data_dir}")
        logger.info(f"Requests file: {self.config.requests_file}")
        logger.info(f"Responses file: {self.config.responses_file}")
        logger.info(f"New messages file: {self.config.new_messages_file}")

        # Check for bot token
        if not self.config.bot_token:
            logger.warning("TG_BOT_TOKEN not set in environment")

        # Ensure files exist
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.config.requests_file.exists():
            with open(self.config.requests_file, "w") as f:
                json.dump({"requests": []}, f)
        if not self.config.responses_file.exists():
            with open(self.config.responses_file, "w") as f:
                json.dump({"responses": {}}, f)
        if not self.config.new_messages_file.exists():
            with open(self.config.new_messages_file, "w") as f:
                json.dump({"messages": []}, f)

        # Start file watcher for outgoing requests
        self.watcher = FileWatcher(
            self.config.requests_file,
            self._handle_file_change,
        )
        self.watcher.start()

        # Start Telegram long polling for incoming messages
        if self.config.bot_token:
            self.poller = TelegramLongPoller(
                bot_token=self.config.bot_token,
                messages_file=self.config.new_messages_file,
                timeout=30,
            )
            self.poller.start()
            logger.info("Started Telegram long polling")
        else:
            logger.warning("No bot token - long polling disabled")

        self._running = True

        # Run loop
        try:
            while self._running:
                # Poll for new Telegram messages
                if self.poller:
                    self.poller.poll()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the daemon."""
        logger.info("Stopping OpsProxy daemon")
        self._running = False
        if self.watcher:
            self.watcher.stop()
        if self.poller:
            self.poller.stop()
            self.poller.close()
        self.http_client.close()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(prog="ops-proxy", description="OpsProxy daemon")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Data directory (default: ~/.openclaw-ops/ops-proxy/)",
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run in foreground (don't daemonize)",
    )
    args = parser.parse_args()

    daemon = OpsProxyDaemon(args.data_dir)

    # Handle signals
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}")
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    daemon.start()


if __name__ == "__main__":
    main()
