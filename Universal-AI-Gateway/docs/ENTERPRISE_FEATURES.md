# 🚀 Enterprise Features

The Universal LLM Gateway provides a suite of advanced features designed to optimize cost, latency, and security for large-scale AI deployments.

---

## 🧠 Semantic Caching

Unlike exact-match caching, semantic caching identifies prompts that are conceptually similar, even if they aren't identical.

- **Vectorization**: Converts prompts into high-dimensional vectors using an embedding model.
- **Search**: Leverages **RediSearch** (KNN similarity, HNSW index) for sub-50ms retrieval.
- **Threshold**: Configurable cosine similarity threshold (defaults to 0.95).
- **Bypass**: Clients can send `X-Cache-Bypass: true` to force a cache miss.
- **Status**: Response includes `X-Cache-Status: HIT | MISS | BYPASS`.
- **Efficiency**: Reduces redundant LLM calls by up to 80% for repetitive workloads.

---

## 🏁 Model Ensembling (Racing)

Achieve the lowest possible latency and highest availability by racing multiple models concurrently.

**Trigger**: Include in request body:
```json
{
  "ensemble_strategy": "fastest",
  "ensemble_models": ["gpt-4o", "gemini-1.5-pro"]
}
```

- **Fastest Wins**: The gateway dispatches the request to all listed models concurrently using `asyncio.as_completed`. The first successful response wins; all others are cancelled.
- **Fallback Safety**: If one provider is on an open circuit or fails, the other fulfills the request.

---

## 💰 Financial Guardrails & Budgeting

Manage AI spend with precision using the `BudgetManager` (Redis-backed).

- **Atomic Tracking**: Uses Redis `INCRBYFLOAT` for race-condition-free cost accumulation per tenant.
- **Daily Caps**: Configurable per-API-key via `--budget` option in the CLI.
- **Two-Stage Alerting**:
  - **80% Threshold** → Fires `BUDGET_WARNING` webhook via `Notifier`. Request is still allowed.
  - **100% Threshold** → Fires `BUDGET_EXCEEDED` webhook and returns `402 Payment Required`.
- **Admin Suite**: Manage tenant budgets via `scripts/cli.py` (e.g. `keys create --budget 10.0`).
- **Visibility**: Every successful response includes `X-Tenant-Budget-Remaining` header.

---

## 🌐 Multi-Provider Routing

The `RoutingEngine` dispatches requests to the optimal provider based on the requested model name.

**Supported Providers** (all verified in `app/providers/`):

| Provider | Module | Example Models |
| :--- | :--- | :--- |
| OpenAI | `openai_provider.py` | `gpt-4o`, `gpt-3.5-turbo` |
| Anthropic | `anthropic_provider.py` | `claude-3-5-sonnet`, `claude-3-opus` |
| Google Gemini | `google_provider.py` | `gemini-1.5-pro`, `gemini-1.5-flash` |
| AWS Bedrock | `bedrock_provider.py` | `anthropic.claude-v2`, `amazon.titan-*` |

---

## 🛡️ Content Safety & Guardrails

- **Regex Protection**: `PromptSafetyScrubber` runs before routing. Detects prompt injection, DAN attempts, and system prompt leakage probes. Request blocked with `403 policy_violation`.
- **Text Normalization**: Input is normalized before scanning to defeat whitespace/case obfuscation.
- **PII Redaction**: When `LOG_PII_REDACTION=true`, emails, SSNs, and credit cards in messages are masked **before logging** (provider sees unmasked content).
- **Circuit Breakers**: Per-provider state machines in Redis. On repeated failure, the circuit opens to prevent cascading timeouts.

---

## 📊 Observability

- **Prometheus Metrics**: `GET /metrics` — request counts, latency histograms, token and cost counters.
- **OpenTelemetry Tracing**: Span-level tracing for cache lookup, provider invocation, and token counting. Toggle via `ENABLE_TRACING=true/false`.
- **Structured JSON Logging**: All logs are structured JSON with `request_id`, `tenant_id`, `latency_ms`, and `status_code`.
- **Webhook Alerts**: `Notifier` service dispatches alerts to `WEBHOOK_URL` for budget events and circuit state changes.
