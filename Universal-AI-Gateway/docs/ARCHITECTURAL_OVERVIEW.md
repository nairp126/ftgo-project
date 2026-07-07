# 🏗️ Architectural Overview

The Universal LLM Gateway is designed for high-throughput, low-latency LLM orchestration with enterprise security and observability.

---

## 📐 Layered Architecture

The system is composed of five distinct layers processed in strict order per request:

1. **Ingress Layer**: FastAPI routes — standardizing OpenAI-compatible requests. Entry point: `POST /v1/chat/completions`.
2. **Guardrail Layer**: `AuthenticationMiddleware` (API key validation, rate limiting, correlation IDs) → `BudgetManager` (pre-flight 402 check) → `PromptSafetyScrubber` (403 on policy violation).
3. **Intelligence Layer**: `CacheManager` (exact-match + RediSearch semantic) → `RoutingEngine` or `ModelEnsembler`.
4. **Adapter Layer**: Provider-specific clients (OpenAI, Anthropic, Google Gemini, AWS Bedrock) with per-provider `CircuitBreaker`.
5. **Observability Layer**: `RequestLogger` (PostgreSQL persistence), `metrics` (Prometheus), OpenTelemetry tracing (configurable via `ENABLE_TRACING`).

---

## 🔄 Request Lifecycle (Sequence Diagrams)

### 1. Standard (Non-Cached) Request

```mermaid
sequenceDiagram
    participant C as Client
    participant MW as Auth Middleware
    participant BM as Budget Manager
    participant PS as Prompt Safety
    participant CM as Cache Manager
    participant RE as Routing Engine
    participant P as Provider (OAI/ANT/GEM)
    participant RL as Request Logger

    C->>MW: POST /v1/chat/completions (Bearer key)
    MW->>MW: Validate key (Argon2), attach correlation ID
    MW->>BM: check_budget(tenant_id, daily_cost_limit)
    BM-->>MW: 402 if exceeded, else continue
    MW->>PS: verify_safety(messages)
    PS-->>MW: 403 if policy_violation, else continue
    MW->>CM: Cache lookup (exact / semantic)
    alt Cache HIT
        CM-->>C: 200 OK (X-Cache-Status: HIT)
    else Cache MISS
        CM->>RE: route_request(chat_request)
        RE->>P: Dispatch to best provider
        P-->>RE: LLM Response
        RE->>CM: Store in cache
        RE->>BM: add_cost(tenant_id, cost_usd)
        RE->>RL: log_request_async (PostgreSQL)
        RE-->>C: 200 OK (with all X-* headers)
    end
```

### 2. Streaming Request

When `stream: true`, the router calls `stream_request()` which returns an async generator. The gateway wraps it in a `StreamingResponse` with `Content-Type: text/event-stream`. Logging and cost tracking happen in a `finally` block after the stream is fully consumed.

```mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant P as Provider

    C->>G: POST /v1/chat/completions (stream: true)
    G->>P: stream_request()
    loop SSE Chunks
        P-->>G: data: {...}\n\n
        G-->>C: data: {...}\n\n
    end
    G-->>C: data: [DONE]\n\n
    Note over G: finally block: log + cost tracking
```

### 3. Model Ensembling (Race Mode)

Triggered when the request body includes `ensemble_strategy: "fastest"` and `ensemble_models: [...]`.

```mermaid
sequenceDiagram
    participant G as Gateway Ensembler
    participant P1 as Provider 1 (GPT-4o)
    participant P2 as Provider 2 (Gemini 1.5)

    G->>P1: Async Task
    G->>P2: Async Task
    Note over G: asyncio.as_completed()
    P1-->>G: Returns first (wins)
    G-->>G: Cancel Task P2
    G-->>Client: Return P1 Response
```

---

## 🛠️ Component Interactions

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Redis** | `aioredis` | Rate limit buckets, exact-match cache, circuit breaker states, budget tracking |
| **RediSearch** | Redis module | Vector indexing (HNSW) for semantic similarity search |
| **PostgreSQL** | `asyncpg` + SQLAlchemy | Persistent `request_logs`, `tenants`, `api_keys` tables |
| **Notifier** | `httpx` | Fires `BUDGET_WARNING` (80%) and `BUDGET_EXCEEDED` (100%) webhooks |
| **OpenTelemetry** | `opentelemetry-sdk` | Distributed tracing (disabled via `ENABLE_TRACING=false`) |
