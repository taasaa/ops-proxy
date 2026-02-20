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

### Inbox-Based Message Flow

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

Outbound HTTP requests from OpenClaw. Read by the daemon.

```json
{
  "requests": [
    {
      "id": "msg-1",
      "method": "POST",
      "url": "https://api.telegram.org/bot<token>/sendMessage",
      "headers": {"Content-Type": "application/json"},
      "body": {"chat_id": "123456", "text": "Hello!"},
      "status": "pending"
    }
  ]
}
```

**Simplified format** - use the `send` shorthand:

```json
{
  "requests": [
    {
      "id": "msg-1",
      "method": "POST",
      "url": "",
      "headers": {},
      "body": {
        "send": {
          "chat_id": "123456",
          "text": "Hello!"
        }
      },
      "status": "pending"
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

## Configuration

`~/.openclaw-ops/ops-proxy/config.yaml`:

```yaml
token_env: TG_BOT_TOKEN
hook_url: http://127.0.0.1:18790/hooks/wake
hook_token: your-hook-secret
allowed_urls:
  - "^https://api\\.telegram\\.org/bot[0-9]+:[A-Za-z0-9_-]+/.*"
max_body_size: 1048576
max_response_size: 1048576
request_timeout: 30
log_level: INFO
```

## Quick Start

```bash
# Install
cd ~/dev/ops/ops-proxy
pip install -e .

# Configure
export TG_BOT_TOKEN="your:telegram_token"
export HOOK_TOKEN="your-hook-secret"

# Run
ops-proxy start
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
    "method": "POST",
    "url": "https://api.telegram.org/bot<token>/sendMessage",
    "headers": {"Content-Type": "application/json"},
    "body": {"chat_id": "123456", "text": "Hello!"},
    "status": "pending"
  }]
}
```

Or use the simplified `send` format:

```json
{
  "requests": [{
    "id": "msg-1",
    "body": {
      "send": {
        "chat_id": "123456",
        "text": "Hello!"
      }
    },
    "status": "pending"
  }]
}
```

Response appears in `responses.json`.

### Inbound Messages (Telegram → OpenClaw)

1. User messages Telegram bot
2. Daemon receives via long-polling
3. Daemon saves to `inbox.json`
4. Daemon calls OpenClaw hook (`/hooks/wake`)
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

# Run in debug mode
python -m ops_proxy.cli --debug
```
