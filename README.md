# ops-proxy

OpsProxy is a daemon for controlled network access. It validates HTTP requests against allowed URL patterns and executes them on behalf of other processes.

## Features

- URL allowlist validation using regex patterns
- Request/response handling via JSON files
- File-based API (scratchpad format)
- Automatic request processing via file watcher
- Configurable via YAML

## Installation

```bash
cd ~/dev/ops/ops-proxy
pip install -e .
```

Or with dev dependencies:

```bash
pip install -e ".[dev]"
```

## Configuration

The default data directory is `~/.openclaw-ops/ops-proxy/`.

### Default Configuration

```yaml
version: "1.0"
token_env: TG_BOT_TOKEN
allowed_urls:
  - ^https://api\.telegram\.org/bot[0-9]+:[A-Za-z0-9_-]+/
max_body_size: 1048576
request_timeout: 30
log_level: INFO
```

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `token_env` | Environment variable name for bot token | `TG_BOT_TOKEN` |
| `allowed_urls` | List of regex patterns for allowed URLs | Telegram API only |
| `max_body_size` | Maximum request body size in bytes | 1048576 (1MB) |
| `request_timeout` | HTTP request timeout in seconds | 30 |
| `log_level` | Logging level | INFO |

## API / Scratchpad Format

OpsProxy uses JSON files for request/response communication.

### requests.json

Add pending requests to `~/.openclaw-ops/ops-proxy/requests.json`:

```json
{
  "requests": [
    {
      "id": "request-1",
      "method": "POST",
      "url": "https://api.telegram.org/bot<token>/sendMessage",
      "headers": {
        "Content-Type": "application/json"
      },
      "body": {
        "chat_id": 123456789,
        "text": "Hello from ops-proxy!"
      },
      "status": "pending"
    }
  ]
}
```

#### Request Fields

| Field | Description | Required |
|-------|-------------|----------|
| `id` | Unique request identifier | Yes |
| `method` | HTTP method (GET, POST, etc.) | No, defaults to POST |
| `url` | Target URL (use `<token>` placeholder for bot token) | Yes |
| `headers` | HTTP headers | No |
| `body` | Request body (JSON object) | No |
| `status` | Request status (pending, completed, failed) | No, defaults to pending |

### responses.json

Responses are written to `~/.openclaw-ops/ops-proxy/responses.json`:

```json
{
  "responses": {
    "request-1": {
      "status": 200,
      "body": {
        "ok": true,
        "result": {
          "message_id": 123,
          "chat": { "id": 123456789 },
          "text": "Hello from ops-proxy!"
        }
      },
      "received_at": "2024-01-15T10:30:00+00:00",
      "error": null
    }
  }
}
```

## Running as a Daemon

### Basic Usage

```bash
ops-proxy
```

### Options

```bash
ops-proxy --help
```

Options:
- `--version`: Show version
- `--data-dir PATH`: Custom data directory (default: ~/.openclaw-ops/ops-proxy/)
- `--foreground`: Run in foreground (don't daemonize)

### Systemd Service (macOS launchd)

The project includes a launchd plist file (`com.openclaw.ops-proxy.plist`) for running as a service on macOS.

1. Copy the plist file:
   ```bash
   cp com.openclaw.ops-proxy.plist ~/Library/LaunchAgents/
   ```

2. Edit the plist to set your environment variables and paths

3. Load the service:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.openclaw.ops-proxy.plist
   ```

4. Start the service:
   ```bash
   launchctl start com.openclaw.ops-proxy
   ```

### Setting the Bot Token

Set the bot token environment variable before starting:

```bash
export TG_BOT_TOKEN="your-bot-token-here"
ops-proxy
```

Or add it to your shell profile (~/.zshrc):

```bash
export TG_BOT_TOKEN="your-bot-token-here"
```

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Project Structure

```
ops-proxy/
├── ops_proxy/
│   ├── __init__.py      # Version info
│   ├── cli.py           # Main daemon entry point
│   ├── config.py        # Configuration loader
│   ├── http_client.py   # HTTP client with validation
│   ├── rules.py         # URL validation rules
│   └── watcher.py       # File watcher for requests
├── tests/               # Test suite
├── pyproject.toml       # Project configuration
└── com.openclaw.ops-proxy.plist  # launchd plist
```

## License

Proprietary - All rights reserved
