# 🛡️ Security Model

The Universal LLM Gateway is built with a "Security-First" architecture to protect both the gateway infrastructure and the sensitive data passing through it.

---

## 1. Authentication Layer

- **API Key Hashing**: Keys are stored using **Argon2id** — the winner of the Password Hashing Competition. Even if the database is breached, raw keys cannot be recovered.
- **Constant-Time Verification**: All key comparisons use `secrets.compare_digest()` to prevent side-channel timing attacks.
- **Multi-Tenant Isolation**: Every request is scoped to a `tenant_id`. Budgets, rate limits, and logs are strictly isolated per tenant.

## 2. Public vs. Protected Paths

The `AuthenticationMiddleware` allows unauthenticated access only to a defined whitelist:

```
/         /health       /docs
/redoc    /openapi.json /metrics
```

All other paths (including `/v1/chat/completions`) require a valid `Authorization: Bearer` header. The middleware also injects `X-Request-ID` and `X-Correlation-ID` on every response for traceability.

## 3. Dynamic Guardrails

### Prompt Injection Mitigation

Handled by `PromptSafetyScrubber` before the request reaches the routing engine.

- **Text Normalization**: Input is normalized (whitespace, case) before scanning to defeat obfuscation attempts.
- **Pattern Matching**: Detects "Ignore previous instructions", "DAN" mode attempts, and system prompt leakage probes.
- **Action**: Blocked with `403 Forbidden`, error code `policy_violation`, including the `matched_pattern` field in the response.

### PII Redaction

Controlled by `settings.logging.log_pii_redaction`. When enabled:

- Emails, SSNs, credit card numbers, and phone numbers in `message.content` are masked before logging.
- Redaction uses a multi-step regex pipeline — **content is not modified** for the provider call, only for storage.

## 4. Financial Budget Enforcement

Enforced by `BudgetManager` (Redis-backed) before the provider call:

- **80% Threshold**: Fires a `BUDGET_WARNING` webhook notification — request is still allowed.
- **100% Threshold**: Fires a `BUDGET_EXCEEDED` webhook notification and raises `BudgetExceededError`, returning `402 Payment Required`.
- **Atomic Tracking**: Uses Redis `INCRBYFLOAT` for race-condition-free cost accumulation.

## 5. Resilience & Defense-in-Depth

- **Distributed Circuit Breaker**: Global circuit states stored in Redis. If a provider exceeds failure thresholds, the circuit opens to prevent cascading failures.
- **Rate Limiting**: Redis-backed Token Bucket algorithm prevents DoS attacks and enforces fair usage per API key.
- **Non-Root Container**: The `Dockerfile` runs the application as a non-root user (`appuser`).

## 6. Logging & Audit

- **Immutable Request Logs**: Every request is logged to `request_logs` in PostgreSQL with a unique `request_id` (UUID).
- **Sanitization**: All logged payloads are PII-scrubbed before storage.
- **Structured JSON**: All logs are emitted as structured JSON for integration with SIEM tools.

## 📡 Security Response Headers

The gateway injects the following headers on every response:

- `X-Request-ID` — unique request identifier.
- `X-Correlation-ID` — OpenTelemetry trace ID.
- `Strict-Transport-Security` (HSTS)
- `Content-Security-Policy` (CSP)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
