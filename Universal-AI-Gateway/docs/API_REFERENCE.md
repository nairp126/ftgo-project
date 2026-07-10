# 📖 API Reference

Comprehensive, ground-truth specification for the Universal LLM Gateway API — verified directly against the live source code.

---

## 🟢 Public Endpoints

### Health Check

`GET /health` — No authentication required. Returns `{"status": "ok"}`.

### Prometheus Metrics

`GET /metrics` — No authentication required. Returns OpenMetrics-compatible Prometheus data.

### Interactive Docs

`GET /docs` — Swagger UI (when running locally). Also available at `/redoc`.

---

## 🔐 Chat Completions

### `POST /v1/chat/completions`

OpenAI-compatible chat completion endpoint.

**Authentication**: `Authorization: Bearer <GATEWAY_API_KEY>` header required on all `POST /v1/*` routes.

**Request Body** (Selected Fields):

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `model` | string | ✅ | Model ID (e.g. `gpt-4o`, `gemini-1.5-pro`). Use `auto` for gateway default. |
| `messages` | array | ✅ | List of `{role, content}` objects. |
| `stream` | boolean | ❌ | If `true`, returns an SSE stream. Default: `false`. |
| `temperature` | float | ❌ | Sampling temperature (0–2). |
| `max_tokens` | integer | ❌ | Maximum tokens to generate. |
| `ensemble_strategy` | string | ❌ | `"fastest"` — enables Model Racing mode. |
| `ensemble_models` | array | ❌ | List of model IDs to race (used with `ensemble_strategy`). |

**Custom Request Headers**:

| Header | Description |
| :--- | :--- |
| `X-Cache-Bypass: true` | Forces a cache miss and refreshes the entry. |

**Response Headers** (on all `2xx` responses):

| Header | Description |
| :--- | :--- |
| `X-Request-ID` | Unique UUID for this request (correlation). |
| `X-Correlation-ID` | Trace ID aligned with OpenTelemetry spans. |
| `X-Provider` | Provider that served the request (e.g. `openai`, `anthropic`, `google`). |
| `X-Cache-Status` | `HIT` \| `MISS` \| `BYPASS`. |
| `X-Response-Time-Ms` | Gateway end-to-end latency in milliseconds. |
| `X-Tenant-Budget-Remaining` | Remaining daily USD budget for the tenant (omitted if no budget configured). |

> [!NOTE]
> `X-Request-ID` and `X-Correlation-ID` are also injected by the `AuthenticationMiddleware` on **every** response, including errors.

**Streaming Response**: When `stream: true`, the gateway returns `Content-Type: text/event-stream` (SSE). Each chunk is a `data: {...}\n\n` line. The last chunk is `data: [DONE]\n\n`.

---

## 🛑 Error Codes

| Status | Code | Meaning |
| :--- | :--- | :--- |
| `401` | `invalid_api_key` | API key is missing, invalid, or has been revoked. |
| `402` | `budget_exceeded` | Tenant has exceeded their configured daily USD spend limit. |
| `403` | `policy_violation` | Prompt was flagged for injection attempt or unsafe content. |
| `422` | `validation_error` | Request body failed Pydantic schema validation. |
| `429` | `rate_limit_exceeded` | Too many requests for this API key (token-bucket enforced). |
| `502` | `provider_error` | The downstream LLM provider returned an error. |
| `503` | `circuit_breaker_open` | Provider circuit breaker is open due to repeated failures. |
| `500` | `internal_server_error` | Unhandled exception (includes `correlation_id` in response body). |

> [!IMPORTANT]
> All error responses include a `correlation_id` field in the body for log tracing.

---

## 🛠️ Admin & Management Interfaces

The gateway offers both a **REST Admin API** (for programmatic control and integrations) and an **Admin CLI tool** (for interactive management).

### Admin REST API

All admin endpoints require authentication via the `X-Admin-Token` header containing your configured `ADMIN_API_KEY`.

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/admin/api-keys` | `GET` | List all API keys. Supports `limit` query param (default 100). |
| `/admin/api-keys` | `POST` | Create a new API key. Request body: `{"tenant_id": "<uuid>", "name": "<name>", "rate_limit": 60}`. Returns the `raw_key` (only shown once). |
| `/admin/api-keys/{key_id}/rotate` | `POST` | Rotate an existing API key. Returns a new key and deactivates the old one. |
| `/admin/api-keys/{key_id}` | `DELETE` | Revoke (deactivate) an API key. |
| `/admin/analytics` | `GET` | Retrieve usage statistics, average latency, cache hit rate, and total cost. |
| `/admin/logs` | `GET` | Retrieve recent request logs. Supports `limit` query param (default 100). |
| `/admin/logs/export` | `POST` | Trigger an export of request logs to S3. |
| `/admin/config/reload` | `POST` | Hot-reload the configuration settings from environment variables without restarting. |

### Admin CLI (`scripts/cli.py`)

Run these commands from the project root using your Python virtual environment:

- **Interactive Setup**: `python scripts/cli.py setup` (creates your first tenant and API key)
- **Check Health**: `python scripts/cli.py health` (verifies database connectivity)
- **View Stats**: `python scripts/cli.py stats` (displays quick real-time request and cost statistics)
- **Tenants**:
  - List: `python scripts/cli.py tenants list`
  - Create: `python scripts/cli.py tenants create "<Name>"`
  - Delete: `python scripts/cli.py tenants delete "<Name>"`
- **API Keys**:
  - List: `python scripts/cli.py keys list`
  - Create: `python scripts/cli.py keys create "<Tenant Name>" "<Key Name>" --limit 60 --budget 10.0 --models "gpt-4o,gemini-1.5-pro"`
  - Rotate: `python scripts/cli.py keys rotate <prefix>`
  - Revoke: `python scripts/cli.py keys revoke <prefix>`

