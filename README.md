# OpsProxy

Local proxy daemon that gives OpenClaw controlled access to Telegram Bot API.

## Purpose

OpenClaw runs with `network: "none"` (security model). This daemon provides controlled outbound access while maintaining security:

```
OpenClaw (no network) ←→ OpsProxyDaemon ←→ Telegram API
                      (localhost only)
```

## Architecture

- **Daemon**: Python, runs outside OpenClaw sandbox
- **Communication**: Scratchpad files + OpenClaw hooks
- **Security**: URL whitelist, token-based auth

### Message Flow

```
Telegram → Long Polling → inbox.json → /hook/wake → OpenClaw reads inbox
                                                          ↓
                                              writes requests.json
                                                          ↓
                                              OpsProxy executes → responses.json
```

1. **Telegram → Long Polling**: Daemon polls Telegram Bot API using long polling
2. **inbox.json**: Telegram messages are stored in the inbox file
3. **/hook/wake**: Daemon notifies OpenClaw via webhook to read the inbox
4. **OpenClaw reads inbox**: Agent reads `~/.openclaw-ops/ops-proxy/inbox.json`
5. **requests.json**: OpenClaw writes HTTP requests to execute
6. **OpsProxy executes**: Daemon processes requests and writes responses to `responses.json`

## Files

### inbox.json

Incoming Telegram messages. Written by the Telegram long poller.

```json
{
  "messages": [
    {
      "update_id": 123456789,
      "message": {
        "message_id": 1,
        "from": {"id": 123456, "is_bot": false, "first_name": "User"},
        "chat": {"id": 123456, "type": "private"},
        "date": 1700000000,
        "text": "Hello"
      }
    }
  ]
}
```

### requests.json

Outbound requests from OpenClaw. Read by the daemon.

**Unified format (supported):**

```json
{
  "requests": [
    {
      "id": "msg-1",
      "command": "send",
      "status": "pending",
      "payload": {
        "chat_id": "123456",
        "text": "Hello!"
      }
    }
  ]
}
```

### responses.json

HTTP responses from executed requests. Written by the daemon.

```json
{
  "responses": {
    "msg-1": {
      "status": 200,
      "body": {"ok": true, "result": {"message_id": 1, "chat": {...}}},
      "received_at": "2024-01-01T12:00:00Z",
      "error": null
    }
  }
}
```

## Unified Request Format

The unified format uses `command` and `payload` keys:

```json
{
  "id": "unique-request-id",
  "command": "send",
  "status": "pending",
  "payload": {
    "chat_id": "123456789",
    "text": "Message text",
    "path": "/path/to/file.pdf",
    "format": "markdown"
  }
}
```

### Payload Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `chat_id` | string | Yes | Telegram chat ID |
| `text` | string | No* | Message text (required if path not provided) |
| `path` | string | No* | File path to upload (required if text not provided) |
| `format` | string | No | Parse mode: `markdown`, `html`, or `plain` (default: `plain`) |

*At least one of `text` or `path` is required.

### Examples

**Send a text message:**

```json
{
  "requests": [{
    "id": "msg-1",
    "command": "send",
    "payload": {
      "chat_id": "123456789",
      "text": "Hello, world!"
    }
  }]
}
```

**Send with Markdown formatting:**

```json
{
  "requests": [{
    "id": "msg-2",
    "command": "send",
    "payload": {
      "chat_id": "123456789",
      "text": "Hello *bold* and _italic_!",
      "format": "markdown"
    }
  }]
}
```

**Send with HTML formatting:**

```json
{
  "requests": [{
    "id": "msg-3",
    "command": "send",
    "payload": {
      "chat_id": "123456789",
      "text": "Hello <b>bold</b> and <i>italic</i>!",
      "format": "html"
    }
  }]
}
```

**Upload a document with caption:**

```json
{
  "requests": [{
    "id": "doc-1",
    "command": "send",
    "payload": {
      "chat_id": "123456789",
      "text": "Here is the document you requested",
      "path": "/home/user/document.pdf"
    }
  }]
}
```

## Configuration

`~/.openclaw-ops/ops-proxy/config.yaml`:

```yaml
token_env: TG_BOT_TOKEN
hook_url: http://127.0.0.1:18790/hook/agent
hook_token: your-hook-secret
allowed_urls:
  - "^https://api\\.telegram\\.org/bot[0-9]+:[A-Za-z0-9_-]+/.*"
max_body_size: 1048576
max_response_size: 1048576
request_timeout: 30
log_level: INFO
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `token_env` | `TG_BOT_TOKEN` | Environment variable for Telegram bot token |
| `hook_url` | `http://127.0.0.1:18790/hook/agent` | OpenClaw hook URL |
| `hook_token` | - | Token for hook authentication |
| `allowed_urls` | Telegram API pattern | List of allowed URL regex patterns |
| `max_body_size` | 1048576 (1MB) | Maximum request body size |
| `max_response_size` | 1048576 (1MB) | Maximum response size |
| `request_timeout` | 30 | HTTP request timeout in seconds |
| `log_level` | INFO | Logging level |

## Quick Start

```bash
# Install
cd ~/dev/ops/ops-proxy
pip install -e .

# Configure
export TG_BOT_TOKEN="your:telegram_token"
export HOOK_TOKEN="your-hook-secret"

# Run
ops-proxy
```

## OpenClaw Configuration

Enable hooks in `~/.openclaw-ops/openclaw.json`:

```json
{
  "hooks": {
    "enabled": true,
    "token": "your-hook-secret",
    "path": "/hooks"
  }
}
```

## Usage

### Outbound Messages (OpenClaw → Telegram)

Write to `~/.openclaw-ops/ops-proxy/requests.json`:

```json
{
  "requests": [{
    "id": "msg-1",
    "command": "send",
    "payload": {
      "chat_id": "123456789",
      "text": "Hello from OpenClaw!"
    }
  }]
}
```

Response appears in `responses.json`.

### Inbound Messages (Telegram → OpenClaw)

1. User messages Telegram bot
2. Daemon receives via long-polling
3. Daemon saves to `inbox.json`
4. Daemon calls OpenClaw hook (`/hook/wake`)
5. OpenClaw reads `inbox.json` and processes messages

## Security

- No network for OpenClaw agent
- Daemon validates all URLs against whitelist
- Hook authentication via Bearer token
- Localhost-only access to OpenClaw

## Development

```bash
# Test
python -m pytest tests/

# Run in foreground
python -m ops_proxy.cli --foreground
```
