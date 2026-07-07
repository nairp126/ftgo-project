# 🚀 Usage Guide

This guide covers how to interact with the Universal LLM Gateway using `curl` and Python.

---

## 🔑 Authentication

Every request to `/v1/*` must include your gateway API key:

```bash
Authorization: Bearer <YOUR_GATEWAY_KEY>
```

Keys are created and managed via the admin CLI (see [Admin CLI](#-administrative-cli) below).

---

## 💬 Basic Chat Completion

The gateway is fully OpenAI-compatible. Any client that works with OpenAI will work here with just a base URL change.

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Explain semantic caching in one sentence."}]
  }'
```

---

## 📡 Streaming

Set `stream: true` to receive a Server-Sent Events (SSE) response:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Tell me a story."}],
    "stream": true
  }'
```

Each chunk is a `data: {...}\n\n` line. The response ends with `data: [DONE]\n\n`.

---

## 🏁 Model Racing (Ensembling)

Race multiple providers concurrently. The **fastest** successful response wins. Trigger via **request body fields** (not a header):

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "What is 2+2?"}],
    "ensemble_strategy": "fastest",
    "ensemble_models": ["gpt-4o", "gemini-1.5-flash"]
  }'
```

> [!NOTE]
> Both `ensemble_strategy` and `ensemble_models` must be set together. The gateway uses `asyncio.as_completed` internally — whichever provider responds first wins; the others are cancelled.

---

## 🌐 Multi-Provider Routing

Route to specific providers by using a model name associated with that provider:

| Provider | Example Models |
| :--- | :--- |
| **OpenAI** | `gpt-4o`, `gpt-3.5-turbo` |
| **Anthropic** | `claude-3-5-sonnet-20241022` |
| **Google Gemini** | `gemini-1.5-pro`, `gemini-1.5-flash` |
| **AWS Bedrock** | `anthropic.claude-v2`, `amazon.titan-*` |

---

## 🧠 Semantic Cache Control

The gateway automatically caches responses using semantic similarity. You can control this per-request:

- **Bypass Cache**: Add `X-Cache-Bypass: true` request header.
- **Check Status**: Inspect the `X-Cache-Status` response header (`HIT` | `MISS` | `BYPASS`).

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "X-Cache-Bypass: true" \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  ...
```

---

## 💡 Reading Response Headers

Every response includes useful metadata in headers:

| Header | Value |
| :--- | :--- |
| `X-Request-ID` | Unique UUID for this request |
| `X-Correlation-ID` | OpenTelemetry trace ID |
| `X-Provider` | Which provider served the request |
| `X-Cache-Status` | `HIT`, `MISS`, or `BYPASS` |
| `X-Response-Time-Ms` | Gateway latency in ms |
| `X-Tenant-Budget-Remaining` | Remaining daily USD budget |

---

## 🎛️ Administrative CLI

Manage the gateway using the interactive CLI at `scripts/cli.py`. Run all commands from the project root.

### Interactive Setup (First-Time)

```bash
python scripts/cli.py setup
```

Guides you through creating a tenant and first API key.

### Tenant Management

```bash
python scripts/cli.py tenants list
python scripts/cli.py tenants create "Acme Corp"
python scripts/cli.py tenants delete "Acme Corp"   # prompts for confirmation
```

### API Key Management

```bash
# List all keys (shows budget, models, rate limit, status)
python scripts/cli.py keys list

# Create a key with budget and model restrictions
python scripts/cli.py keys create "Acme Corp" "Prod Key" \
  --limit 100 \
  --budget 10.0 \
  --models "gpt-4o,gemini-1.5-pro"

# Rotate or revoke
python scripts/cli.py keys rotate <key-prefix>
python scripts/cli.py keys revoke <key-prefix>
```

### System Health & Stats

```bash
python scripts/cli.py health   # Check DB/Redis connectivity
python scripts/cli.py stats    # Live stats from database (requests, cost, latency)
```

---

## 📈 Budget Monitoring

Budget state is tracked atomically in Redis. You can check remaining budget via:

1. **Response header** — `X-Tenant-Budget-Remaining` is included in every API response.
2. **CLI stats** — `python scripts/cli.py stats` shows total cost.
3. **Webhook alerts** — Set `WEBHOOK_URL` in `.env` to receive `BUDGET_WARNING` (80%) and `BUDGET_EXCEEDED` (100%) events automatically.
