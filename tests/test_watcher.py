"""Tests for file watcher module."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from ops_proxy.watcher import FileWatcher, RequestFileHandler


class TestRequestFileHandler:
    """Tests for RequestFileHandler."""

    def test_read_requests_with_pending(self, tmp_path):
        """Test reading pending requests from file."""
        requests_file = tmp_path / "requests.json"

        # Create file with pending requests
        data = {
            "requests": [
                {"id": "req-1", "status": "pending", "command": "send", "payload": {"chat_id": "123", "text": "hello"}},
                {"id": "req-2", "status": "completed", "command": "send", "payload": {"chat_id": "123", "text": "done"}},
                {"id": "req-3", "status": "pending", "command": "send", "payload": {"chat_id": "123", "text": "also pending"}},
            ]
        }
        requests_file.write_text(json.dumps(data))

        callback_calls = []

        def callback(requests):
            callback_calls.append(requests)

        handler = RequestFileHandler(requests_file, callback)
        handler._read_requests()

        # Should have called callback with 2 pending requests
        assert len(callback_calls) == 1
        assert len(callback_calls[0]) == 2
        ids = [r["id"] for r in callback_calls[0]]
        assert "req-1" in ids
        assert "req-3" in ids
        assert "req-2" not in ids

    def test_read_requests_file_not_exists(self, tmp_path):
        """Test reading when file doesn't exist."""
        requests_file = tmp_path / "requests.json"

        callback_calls = []

        def callback(requests):
            callback_calls.append(requests)

        handler = RequestFileHandler(requests_file, callback)
        handler._read_requests()

        # Should not call callback
        assert len(callback_calls) == 0

    def test_read_requests_invalid_json(self, tmp_path):
        """Test reading with invalid JSON."""
        requests_file = tmp_path / "requests.json"
        requests_file.write_text("not valid json")

        callback_calls = []

        def callback(requests):
            callback_calls.append(requests)

        handler = RequestFileHandler(requests_file, callback)
        handler._read_requests()

        # Should not call callback
        assert len(callback_calls) == 0

    def test_read_requests_no_pending(self, tmp_path):
        """Test reading when no pending requests."""
        requests_file = tmp_path / "requests.json"

        data = {
            "requests": [
                {"id": "req-1", "status": "completed"},
            ]
        }
        requests_file.write_text(json.dumps(data))

        callback_calls = []

        def callback(requests):
            callback_calls.append(requests)

        handler = RequestFileHandler(requests_file, callback)
        handler._read_requests()

        # Should not call callback when no pending
        assert len(callback_calls) == 0

    def test_read_requests_empty_file(self, tmp_path):
        """Test reading from empty requests array."""
        requests_file = tmp_path / "requests.json"

        data = {"requests": []}
        requests_file.write_text(json.dumps(data))

        callback_calls = []

        def callback(requests):
            callback_calls.append(requests)

        handler = RequestFileHandler(requests_file, callback)
        handler._read_requests()

        # Should not call callback
        assert len(callback_calls) == 0


class TestRequestFileHandlerOnModified:
    """Tests for on_modified event handling."""

    def test_on_modified_ignores_directory(self, tmp_path):
        """Test that directory events are ignored."""
        requests_file = tmp_path / "requests.json"

        callback_calls = []

        def callback(requests):
            callback_calls.append(requests)

        handler = RequestFileHandler(requests_file, callback)

        # Create a mock directory event
        mock_event = MagicMock()
        mock_event.is_directory = True

        handler.on_modified(mock_event)

        # Should not call callback
        assert len(callback_calls) == 0

    @patch("pathlib.Path.stat")
    def test_on_modified_ignores_same_mtime(self, mock_stat, tmp_path):
        """Test that duplicate events with same mtime are ignored."""
        requests_file = tmp_path / "requests.json"
        requests_file.write_text(json.dumps({"requests": []}))

        # Mock stat to return same mtime
        mock_stat_result = MagicMock()
        mock_stat_result.st_mtime = 12345.0
        mock_stat.return_value = mock_stat_result

        callback_calls = []

        def callback(requests):
            callback_calls.append(requests)

        handler = RequestFileHandler(requests_file, callback)
        handler._last_mtime = 12345.0  # Already processed

        # Create a mock file event
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = str(requests_file)

        handler.on_modified(mock_event)

        # Should not call callback (same mtime)
        assert len(callback_calls) == 0


class TestFileWatcher:
    """Tests for FileWatcher."""

    def test_file_watcher_start_creates_file(self, tmp_path):
        """Test that starting watcher creates requests file if missing."""
        requests_file = tmp_path / "requests.json"

        callback_calls = []

        def callback(requests):
            callback_calls.append(requests)

        watcher = FileWatcher(requests_file, callback)
        watcher.start()

        try:
            # File should exist
            assert requests_file.exists()

            # Should have valid JSON
            data = json.loads(requests_file.read_text())
            assert "requests" in data
        finally:
            watcher.stop()

    def test_file_watcher_start_creates_parent_dir(self, tmp_path):
        """Test that starting watcher creates parent directory."""
        requests_file = tmp_path / "subdir" / "requests.json"

        callback_calls = []

        def callback(requests):
            callback_calls.append(requests)

        watcher = FileWatcher(requests_file, callback)
        watcher.start()

        try:
            # Parent directory should exist
            assert requests_file.parent.exists()
        finally:
            watcher.stop()

    def test_file_watcher_stop(self, tmp_path):
        """Test stopping the file watcher."""
        requests_file = tmp_path / "requests.json"
        requests_file.write_text(json.dumps({"requests": []}))

        callback_calls = []

        def callback(requests):
            callback_calls.append(requests)

        watcher = FileWatcher(requests_file, callback)
        watcher.start()
        watcher.stop()

        # Should have stopped without error
        assert watcher._observer is None
