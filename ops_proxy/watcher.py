"""File watcher for monitoring requests.json."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class RequestFileHandler(FileSystemEventHandler):
    """Handler for requests.json file changes."""

    def __init__(self, requests_file: Path, callback: Callable[[list[dict[str, Any]]], None]):
        self.requests_file = requests_file
        self.callback = callback
        self._last_mtime: float = 0

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return

        # Watchdog can fire multiple events for one change
        try:
            current_mtime = self.requests_file.stat().st_mtime
            if current_mtime == self._last_mtime:
                return
            self._last_mtime = current_mtime
        except OSError:
            pass

        if Path(event.src_path) == self.requests_file:
            logger.debug(f"Detected change in {self.requests_file}")
            self._read_requests()

    def _read_requests(self) -> None:
        """Read pending requests from file."""
        try:
            if not self.requests_file.exists():
                return

            with open(self.requests_file) as f:
                data = json.load(f)

            requests_list = data.get("requests", [])
            pending = [r for r in requests_list if r.get("status") == "pending"]

            if pending:
                logger.info(f"Found {len(pending)} pending requests")
                self.callback(pending)

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in requests file: {e}")
        except Exception as e:
            logger.error(f"Error reading requests file: {e}")


class FileWatcher:
    """File watcher for requests.json."""

    def __init__(self, requests_file: Path, callback: Callable[[list[dict[str, Any]]], None]):
        self.requests_file = requests_file
        self.callback = callback
        self._observer: Observer | None = None
        self._handler: RequestFileHandler | None = None

    def start(self) -> None:
        """Start watching the requests file."""
        # Ensure parent directory exists
        self.requests_file.parent.mkdir(parents=True, exist_ok=True)

        # Ensure file exists with valid structure
        if not self.requests_file.exists():
            with open(self.requests_file, "w") as f:
                json.dump({"requests": []}, f)

        self._handler = RequestFileHandler(self.requests_file, self.callback)
        self._observer = Observer()
        self._observer.schedule(
            self._handler,
            str(self.requests_file.parent),
            recursive=False,
        )
        self._observer.start()
        logger.info(f"Started watching {self.requests_file}")

        # Initial read
        self._handler._read_requests()

    def stop(self) -> None:
        """Stop watching the requests file."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            logger.info("Stopped file watcher")
