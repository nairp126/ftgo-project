# ADR-001: API Gateway Architecture — Universal AI Gateway as Edge Proxy

**Date:** 2026-06-27
**Status:** Accepted
**Owner:** [Person 5]
**Service:** API Gateway Layer

---

## Context

The FTGO food delivery application is being decomposed from a monolith
into six domain microservices: Order Service, Kitchen Service, Restaurant
Service, Accounting Service, Consumer Service, and Order History Service.
These services are deployed on AWS EKS (ap-south-1, Mumbai) and need a
unified entry point for all client traffic.

The FTGO reference implementation ships with its own API gateway —
`ftgo-api-gateway` — built on Spring Cloud Gateway + Spring WebFlux
(Java). This gateway handles two concerns:

1. **Path-based routing** — POST/PUT `/orders` and `/consumers` are
   forwarded directly to their respective backend services via
   Spring Cloud Gateway's `RouteLocator` bean
2. **API composition** — GET `/orders/{orderId}` fans out to four
   services in parallel (Order, Kitchen, Delivery, Accounting) using
   Reactor's `Mono.zip()` and merges results into a single
   `OrderDetails` response

A second gateway exists in this project — the **Universal AI Gateway**
— a self-built FastAPI (Python 3.12) reverse proxy originally designed
for LLM/AI traffic. Its capabilities at the start of this project:

| Capability | Status |
|-----------|--------|
| Per-tenant API key auth (PostgreSQL + Argon2) | ✅ Working |
| Redis-based semantic caching | ✅ Working (LLM-specific) |
| Per-tenant rate limiting | ✅ Working |
| LLM cost budget enforcement | ✅ Working (global — bug) |
| PostgreSQL request logging | ✅ Working |
| S3 audit log archiving | ✅ Working |
| Path-based routing to microservices | ❌ Not implemented |
| Reverse proxy (httpx forwarding) | ❌ Not implemented |
| JWT validation | ❌ Not implemented |
| Health check passthrough | ❌ Not implemented (404) |
| HTTP method cache guard | ❌ Missing (POST could be cached) |

The core question: how do these two gateways work together in the
final Kubernetes architecture?

---

## Decision Drivers

- The Universal AI Gateway represents significant prior engineering work
  and must contribute meaningfully to the deployment — not be sidelined
- FTGO's Spring Cloud Gateway API composition (`Mono.zip()` fan-out with
  partial failure handling) is battle-tested in Reactor — rebuilding this
  in Python within a July deadline introduces unacceptable risk of subtle
  bugs in timeout handling and partial failure cases
- The gateway owner (Person 5) also owns the Kubernetes platform layer —
  bandwidth is insufficient for a full from-scratch gateway rebuild
- All team members need to understand and explain the gateway architecture
  in a viva — it must be clearly explainable
- Kubernetes liveness and readiness probes require `/actuator/health`
  to return 200 — currently returns 404
- FTGO microservices expect downstream identity headers (X-User-ID,
  X-Tenant-ID, X-User-Roles) from the gateway — not raw JWT tokens

---

## Options Considered

### Option A — Replace FTGO gateway entirely with Universal AI Gateway

Rebuild all Spring Cloud Gateway functionality in FastAPI: path-based
routing, API composition fan-out using `asyncio.gather()`, distributed
tracing via OpenTelemetry, and Prometheus metrics. Universal AI Gateway
becomes the single gateway.

**Pros:**
- Single gateway — simpler operational model
- Entire gateway codebase in Python — consistent with team's primary stack
- Strongest portfolio story if executed completely

**Cons:**
- `asyncio.gather()` fan-out with per-service timeouts and partial failure
  fallbacks is complex to implement correctly under deadline pressure
- Spring's `Mono.zip()` implementation gracefully handles upstream 404 vs
  503 — subtle distinction that a fresh implementation often gets wrong
- Distributed tracing from scratch adds additional weeks of work
- Person 5 also owns Kubernetes platform — cannot dedicate full timeline
  to gateway rebuild

### Option B — Two-layer gateway architecture (Chosen)

Universal AI Gateway handles edge concerns. FTGO's Spring Cloud Gateway
handles internal routing and API composition. Traffic flows:
`Client → Universal AI Gateway → FTGO Gateway → Microservices`

**Pros:**
- Preserves FTGO's battle-tested API composition without rebuilding it
- Universal AI Gateway contributes real edge-layer functionality
- Separation of concerns is architecturally clean — each gateway has
  one clear responsibility
- Mirrors production patterns (Netflix uses a similar edge/internal split)
- Achievable within the July deadline

**Cons:**
- Two network hops instead of one — adds ~5-15ms latency within cluster
- Two gateway codebases to maintain and deploy
- If Universal AI Gateway crashes, all traffic stops regardless of
  whether FTGO services are healthy

### Option C — Use FTGO gateway only

Deploy FTGO's Spring Cloud Gateway unchanged. Mention Universal AI Gateway
as a separate portfolio project unrelated to this deployment.

**Pros:**
- Least work, lowest risk

**Cons:**
- Loses the primary differentiator of this project
- Universal AI Gateway contributes nothing to the deployment
- Weakest interview and viva story of the three options

---

## Decision

**We chose Option B — Two-layer gateway architecture.**

FTGO's `Mono.zip()` API composition is a mature reactive implementation
that would take weeks to replicate correctly in Python (Option A).
Option C abandons the primary project differentiator. Option B delivers
a clean separation of concerns — the Universal AI Gateway owns all edge
concerns (auth, rate limiting, observability) and FTGO's gateway owns
all routing concerns (service discovery, API composition). This mirrors
how companies like Netflix separate their edge gateway (Zuul) from
internal routing, and produces a stronger viva narrative than a single
rebuilt gateway.

---

## Architecture

```
Internet
    │
    ▼
[AWS Load Balancer — Ingress Controller]
    │  All external traffic enters here
    ▼
[Universal AI Gateway]           Port: 8000    ← Edge Layer
  · JWT validation (PyJWT)
  · API key authentication (PostgreSQL + Argon2)
  · Per-tenant rate limiting (Redis)
  · Request logging → PostgreSQL
  · Audit archiving → S3
  · Budget enforcement (LLM /v1/* routes only)
  · Semantic caching (LLM /v1/* routes only)
  · Forwards identity as: X-Tenant-ID, X-User-ID, X-User-Roles
    │
    │  Strips: Authorization, X-API-Key, Cookie
    │  Adds:   X-Tenant-ID, X-User-ID, X-Forwarded-For
    ▼
[FTGO API Gateway]               Port: 8080    ← Internal Routing Layer
  · Path-based routing (RouteLocator)
  · API composition — GET /orders/{orderId}
      → parallel fan-out: Order + Kitchen + Delivery + Accounting
      → merged via Mono.zip()
  · Distributed tracing (Spring Cloud Sleuth + Zipkin)
  · Prometheus metrics (Micrometer)
    │
    ├──▶ Order Service         :8080  (Kubernetes DNS: ftgo-order-service)
    ├──▶ Kitchen Service       :8080  (ftgo-kitchen-service)
    ├──▶ Restaurant Service    :8080  (ftgo-restaurant-service)
    ├──▶ Accounting Service    :8080  (ftgo-accounting-service)
    ├──▶ Consumer Service      :8080  (ftgo-consumer-service)
    └──▶ Order History Service :8080  (ftgo-order-history-service)
```

---

## Bugs Fixed Before Integration

The following critical issues were identified via code audit and fixed
before integration:

### Bug 1 — Budget enforcement blocked all authenticated traffic

**File:** `app/middleware/rate_limit.py`

**Problem:** `check_budget(tenant_id)` ran on every authenticated request
globally. A tenant exceeding their LLM token budget received
`402 Payment Required` on `POST /api/orders` even though that request
consumes zero LLM tokens.

**Fix:** Scoped budget check to paths starting with `/v1/` only:
```python
if request.url.path.startswith("/v1/"):
    await self._budget.check_budget(tenant_id)
```

### Bug 2 — Semantic cache had no HTTP method guard

**File:** `app/cache/cache_manager.py`

**Problem:** `should_bypass()` only checked headers, not HTTP method.
`POST /api/orders` could have been served from cache, silently creating
duplicate orders.

**Fix:** Added method check to `should_bypass()`:
```python
if request.method not in ("GET", "HEAD") \
        and request.url.path != "/v1/chat/completions":
    return True
```

### Bug 3 — Health check endpoints returned 404

**Files:** `app/middleware/auth.py`, `app/middleware/rate_limit.py`,
`app/api/health.py`

**Problem:** `/actuator/health` was not registered, not in `PUBLIC_PATHS`,
and not in `EXEMPT_PATHS`. Kubernetes liveness and readiness probes
would fail, causing the gateway pod to be killed and restarted
continuously.

**Fix:** Added to `PUBLIC_PATHS` and `EXEMPT_PATHS`, registered proxy
route forwarding to `$DOWNSTREAM_HEALTH_URL`.

### Bug 4 — No reverse proxy capability

**Files:** `app/core/proxy_config.py` (new), `app/services/proxy.py`
(new), `app/api/routes.py` (modified)

**Problem:** Gateway only forwarded requests to LLM providers via the
provider adapter pattern. No mechanism existed to forward arbitrary HTTP
traffic to microservices.

**Fix:** Built:
- Route table config (`proxy_config.py`) — maps path prefixes to
  upstream URLs with per-route timeouts
- Async `httpx`-based proxy handler (`proxy.py`) — forwards requests,
  strips sensitive headers, injects identity headers, logs latency
- Catch-all route in `routes.py` — registered after all `/v1/*` routes

### Bug 5 — No JWT validation

**Files:** `app/core/jwt_handler.py` (new), `app/middleware/auth.py`
(modified)

**Problem:** Only stateful API key auth existed. FTGO microservices
expect identity propagated via headers. JWT claims were not extracted
or forwarded.

**Fix:** Added PyJWT-based validation alongside existing API key flow.
Identity (`user_id`, `tenant_id`, `roles`) extracted and forwarded
downstream as `X-User-ID`, `X-Tenant-ID`, `X-User-Roles`.

---

## New Files Created

| File | Purpose |
|------|---------|
| `app/core/proxy_config.py` | Route table — prefix to upstream URL mapping |
| `app/services/proxy.py` | Async reverse proxy handler |
| `app/core/jwt_handler.py` | JWT decode, verify, identity extraction |
| `k8s/gateway/deployment.yaml` | Kubernetes Deployment manifest |
| `k8s/gateway/service.yaml` | Kubernetes ClusterIP Service |
| `k8s/gateway/configmap.yaml` | Non-sensitive configuration |
| `k8s/gateway/secret.yaml` | Sensitive config template |
| `k8s/gateway/ingress.yaml` | AWS Load Balancer Controller Ingress |
| `.github/workflows/gateway.yml` | CI/CD pipeline |
| `tests/test_proxy.py` | Integration tests for proxy layer |

---

## Route Table

Defined in `app/core/proxy_config.py`:

| Incoming Path | Upstream | Strip Prefix | Timeout |
|--------------|---------|-------------|---------|
| `/api/orders` | `http://ftgo-api-gateway:8080` | Yes | 30s |
| `/api/consumers` | `http://ftgo-api-gateway:8080` | Yes | 10s |
| `/api/kitchen` | `http://ftgo-api-gateway:8080` | Yes | 10s |
| `/api/restaurants` | `http://ftgo-api-gateway:8080` | Yes | 10s |
| `/api/accounting` | `http://ftgo-api-gateway:8080` | Yes | 10s |
| `/v1/*` | LLM router (not proxied) | — | — |
| `/health` | Local health check (not proxied) | — | — |
| `/admin/*` | Local admin routes (not proxied) | — | — |

---

## Consequences

### Positive
- Universal AI Gateway contributes real edge-layer functionality —
  not a surface-level integration
- FTGO's API composition is preserved without risky reimplementation
- Clean separation of concerns — each gateway has one responsibility
- Full CI/CD pipeline with per-service GitHub Actions workflows
- Request audit trail in PostgreSQL and S3 covers all FTGO traffic

### Negative
- Two network hops add latency per request (~5-15ms within EKS cluster
  using Kubernetes internal DNS)
- Two gateway deployments to manage — additional Kubernetes resources
- If Universal AI Gateway pod crashes, the entire system is unreachable
  regardless of FTGO service health

### Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| POST requests cached causing duplicate orders | Low | Bug 2 fix + `test_proxy.py` covers this explicitly |
| Budget check blocks FTGO traffic | Low | Bug 1 fix + integration test verifies bypass |
| Health probe failure causes pod restart loop | Low | Bug 3 fix + `livenessProbe` configured with failure threshold 3 |
| Two-hop latency noticeable in demo | Low | Both gateways in same EKS cluster — sub-millisecond internal DNS |
| Universal AI Gateway proxy bug causes data loss | Medium | `test_proxy.py` covers header stripping, timeout, 404 passthrough |

---

## References

- Richardson, C. (2018). *Microservices Patterns*. Manning Publications.
  Chapter 8: External API patterns — API Gateway pattern
- Spring Cloud Gateway documentation:
  https://spring.io/projects/spring-cloud-gateway
- Netflix Tech Blog — Zuul 2 (edge vs internal gateway pattern):
  https://netflixtechblog.com/zuul-2-the-netflix-journey-to-asynchronous-non-blocking-systems-45947377fb5c
- Fowler, M. Strangler Fig Application:
  https://martinfowler.com/bliki/StranglerFigApplication.html
- FastAPI documentation — Background tasks and middleware:
  https://fastapi.tiangolo.com/tutorial/middleware/
