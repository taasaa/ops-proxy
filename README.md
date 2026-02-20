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

## Features

- Long-polling Telegram Bot API for incoming messages
- OpenClaw hook notifications for instant message delivery
- Outbound requests via scratchpad file
- URL whitelist validation
- Full audit logging

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

## Configuration

`~/.openclaw-ops/ops-proxy/config.yaml`:

```yaml
token_env: TG_BOT_TOKEN
hook_url: http://127.0.0.1:18790/hooks/wake
allowed_urls:
  - "^https://api\\.telegram\\.org/bot[0-9]+:[A-Za-z0-9_-]+/.*"
```

## Files

- `ops_proxy/cli.py` - Main daemon
- `ops_proxy/telegram.py` - Telegram API client
- `ops_proxy/notifier.py` - OpenClaw hook notifier
- `ops_proxy/rules.py` - URL validation
- `ops_proxy/http_client.py` - HTTP client

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

Response appears in `responses.json`.

### Inbound Messages (Telegram → OpenClaw)

1. User messages Telegram bot
2. Daemon receives via long-polling
3. Daemon calls OpenClaw hook (`/hooks/wake`)
4. OpenClaw queues as system event

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
