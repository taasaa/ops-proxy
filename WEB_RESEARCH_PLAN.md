# OpsProxy Web Research Extension Plan

**Objective:** Enable sandboxed OpenClaw to perform web research through OpsProxy
**Security Level:** TOP PRIORITY
**Recommendation:** Jina AI Reader API (unanimous Council consensus)

---

## 1. API Selection: Jina AI Reader API

### Why Jina AI (Council Consensus)

| Criteria | Brave Search | Jina AI | Perplexity |
|----------|-------------|---------|------------|
| **Architecture Fit** | Good | Excellent | Poor (consumer-focused) |
| **Security Simplicity** | Medium | High | Low |
| **Cost** | $10/10k calls | $10/10k calls | $5/query (expensive) |
| **Output Format** | JSON results | Clean markdown/HTML | Conversational answers |
| **Rate Limits** | 2000/day free | Generous | Strict |
| **Proxy Suitability** | Partial | Designed for this | Not designed |

**Jina AI Reader API:**
- Simple GET request with URL → returns clean extracted content
- Single endpoint, predictable behavior
- Minimal attack surface
- Easy to sanitize/validate output

---

## 2. Unified Search Request Format

Extend existing unified format with `search` command:

```json
{
  "requests": [
    {
      "id": "search-1",
      "command": "search",
      "status": "pending",
      "payload": {
        "engine": "jina",
        "query": "What is the capital of France?",
        "url": "https://example.com/article",
        "options": {
          "format": "markdown",
          "max_length": 8192
        }
      }
    }
  ]
}
```

### Payload Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `engine` | string | Yes | Search engine: `jina`, `brave` |
| `query` | string | No* | Search query text |
| `url` | string | No* | Direct URL to fetch |
| `options.format` | string | No | Output format: `markdown`, `html`, `text` |
| `options.max_length` | int | No | Max response length (default: 8192) |

*At least one of `query` or `url` is required.

### Example: URL Content Extraction

```json
{
  "requests": [{
    "id": "fetch-1",
    "command": "search",
    "payload": {
      "engine": "jina",
      "url": "https://example.com/article"
    }
  }]
}
```

---

## 3. Security Controls

### 3.1 URL Allowlist

```yaml
# config.yaml
allowed_urls:
  # Telegram API (existing)
  - "^https://api\\.telegram\\.org/bot[0-9]+:.*"

  # Jina AI (NEW)
  - "^https://r\\.jina\\.ai/.*"

  # Brave Search (NEW)
  - "^https://api\\.search\\.brave\\.com/.*"

  # Optional: Direct URL fetching (restricted)
  - "^https://r\\.jina\\.ai/http(s)?://.*"
```

### 3.2 Request Validation

```python
# ops_proxy/search.py
class SearchValidator:
    ALLOWED_ENGINES = {"jina", "brave"}
    MAX_QUERY_LENGTH = 500
    MAX_URLS_PER_REQUEST = 10

    def validate(self, payload: dict) -> tuple[bool, str]:
        # 1. Check engine is allowed
        if payload.get("engine") not in self.ALLOWED_ENGINES:
            return False, f"Engine not allowed: {payload.get('engine')}"

        # 2. Check query length
        query = payload.get("query", "")
        if len(query) > self.MAX_QUERY_LENGTH:
            return False, "Query too long"

        # 3. Validate URL if provided
        if "url" in payload:
            url = payload["url"]
            if not self._is_url_safe(url):
                return False, "URL not in allowlist"

        # 4. Check URL count limit
        urls = payload.get("urls", [])
        if len(urls) > self.MAX_URLS_PER_REQUEST:
            return False, "Too many URLs"

        return True, ""
```

### 3.3 Rate Limiting

```yaml
# config.yaml
rate_limits:
  search:
    requests_per_minute: 30
    requests_per_hour: 500
    requests_per_day: 5000
```

### 3.4 Response Sanitization

```python
# Sanitize before passing to OpenClaw
def sanitize_response(content: str, max_length: int = 8192) -> str:
    # 1. Truncate to max length
    if len(content) > max_length:
        content = content[:max_length] + "\n\n[truncated]"

    # 2. Remove potentially dangerous HTML/JS
    content = strip_scripts(content)
    content = strip_iframes(content)

    # 3. Strip tracking parameters from URLs
    content = clean_urls(content)

    return content
```

### 3.5 Network Isolation

```
┌─────────────────────────────────────────────────────────────┐
│                      OpenClaw (sandbox)                     │
│                    network: "none"                          │
└─────────────────────────┬───────────────────────────────────┘
                          │ requests.json (file IPC)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      OpsProxy                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │
│  │   Telegram  │  │   Search    │  │   URL Fetch     │   │
│  │   Handler   │  │   Handler   │  │   Handler       │   │
│  └─────────────┘  └─────────────┘  └─────────────────┘   │
│         │                │                   │              │
│         └────────────────┼───────────────────┘              │
│                          │                                   │
│                    URL Allowlist                             │
│                    Rate Limiting                            │
│                    Response Sanitization                    │
└─────────────────────────┬───────────────────────────────────┘
                          │ responses.json (file IPC)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    OpenClaw (reads response)                │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. OpenClaw Integration

### 4.1 File-Based IPC (Existing)

OpsProxy already uses file-based IPC with OpenClaw. This extends naturally:

```
Agent writes: ~/.openclaw-ops/ops-proxy/requests.json
                    ↓
OpsProxy processes search requests
                    ↓
Agent reads:  ~/.openclaw-ops/ops-proxy/responses.json
```

### 4.2 Agent Usage Example

```python
# OpenClaw agent code (pseudo-code)

# 1. Write search request
search_request = {
    "requests": [{
        "id": "research-1",
        "command": "search",
        "payload": {
            "engine": "jina",
            "query": "latest advances in quantum computing"
        }
    }]
}
write_file("~/.openclaw-ops/ops-proxy/requests.json", search_request)

# 2. Wait for response
while True:
    responses = read_file("~/.openclaw-ops/ops-proxy/responses.json")
    if "research-1" in responses:
        results = responses["research-1"]
        break
    sleep(1)

# 3. Process results
content = results["body"]["content"]
```

### 4.3 Response Format

```json
{
  "responses": {
    "research-1": {
      "status": 200,
      "body": {
        "ok": true,
        "result": {
          "content": "Markdown content from fetched page...",
          "url": "https://example.com/article",
          "engine": "jina"
        }
      },
      "received_at": "2024-01-01T12:00:00Z",
      "error": null
    }
  }
}
```

---

## 5. Implementation Roadmap

### Phase 1: Core Infrastructure (Week 1)

- [ ] Add `search` command to unified format handler
- [ ] Implement `SearchValidator` with URL allowlist
- [ ] Add Jina AI API client
- [ ] Add Brave Search API client (backup)
- [ ] Implement rate limiting
- [ ] Add response sanitization

### Phase 2: Integration & Testing (Week 2)

- [ ] Integrate with existing request processor
- [ ] Write unit tests (search, validation, sanitization)
- [ ] Integration tests with mock APIs
- [ ] Security audit (RedTeam review)

### Phase 3: Documentation & Deployment (Week 3)

- [ ] Update README with search usage
- [ ] Document configuration options
- [ ] Create example agent prompts
- [ ] Deploy to staging, test with real OpenClaw
- [ ] Deploy to production

---

## 6. Configuration

```yaml
# ~/.openclaw-ops/ops-proxy/config.yaml

# Search API keys (environment variables recommended)
search:
  jina_api_key_env: JINA_API_KEY
  brave_api_key_env: BRAVE_API_KEY

# Security
allowed_urls:
  - "^https://api\\.telegram\\.org/bot[0-9]+:.*"
  - "^https://r\\.jina\\.ai/.*"
  - "^https://api\\.search\\.brave\\.com/.*"

# Rate limits
rate_limits:
  search:
    requests_per_minute: 30
    requests_per_hour: 500
    requests_per_day: 5000

# Response limits
max_response_size: 1048576
max_search_content_length: 8192
```

---

## 7. Cost Estimation

| Service | Free Tier | Paid Tier |
|---------|-----------|------------|
| Jina AI | 10k calls/month | $10/10k calls |
| Brave Search | 2k calls/day | $10/10k calls |

For typical OpenClaw usage (occasional research), free tiers likely sufficient.

---

## 8. Security Summary

| Control | Implementation |
|---------|----------------|
| **URL Allowlist** | Regex patterns in config.yaml |
| **API Key Isolation** | Environment variables only |
| **Rate Limiting** | Per-minute/hour/day limits |
| **Response Sanitization** | Strip scripts, iframes, truncate |
| **No Direct Internet** | All traffic via OpsProxy |
| **File IPC** | Existing secure channel |

---

## Recommendation

**Proceed with Jina AI Reader API** as the primary search engine. It offers:
- Best architecture fit for proxy use
- Simplest security model
- Clean output for agent consumption
- Cost-effective (free tier sufficient for most use)

**Backup:** Brave Search if Jina is unavailable or policy changes.

---

*Plan created: 2026-02-20*
