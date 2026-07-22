# Universal AI Gateway

> **Owner:** Pranav Nair ([@nairp126](https://github.com/nairp126))  
> **Part of:** FTGO Microservices Deployment — DevOps Course Project

---

## What This Service Does

The **Universal AI Gateway** serves as the primary edge ingress gateway for the entire FTGO microservice platform and enterprise LLM infrastructure. It provides edge authentication (API Key & PyJWT validation), per-tenant distributed rate limiting (Redis token bucket), header sanitization, correlation ID generation, financial budgeting, and intelligent reverse-proxy routing.

All incoming client traffic enters through this gateway. Requests prefixed with `/v1/chat/completions` are handled by the unified LLM routing & semantic caching engine, while domain API requests prefixed with `/api/*` are dynamically forwarded downstream to the internal **FTGO API Gateway** (`ftgo-api-gateway:8080`).

---

## Domain Responsibilities

**Owns:**
- Tenant identity & multi-tenancy management (`tenants` table)
- API Key lifecycle & secure hashing (`api_keys` table)
- Request audit logging & observability metrics (`request_logs` table)
- Semantic vector cache & exact response caching (Redis / RediSearch)
- Daily USD financial spend limits (`BudgetManager`)
- Dynamic edge reverse-proxy route table (`proxy_config.py`)

**Does NOT own (and never reads directly):**
- Domain microservice databases (`orders`, `kitchen`, `restaurants`, `accounting`, `consumers`, `order_history`)
- Asynchronous Saga orchestration logic (owned by Order Service)
- CQRS read projections (owned by Order History Service)

---

## API Endpoints

| Method | Path | Description | Access Control | Downstream Target |
|--------|------|-------------|----------------|-------------------|
| `POST` | `/v1/chat/completions` | Unified OpenAI-compatible LLM completion endpoint | API Key / JWT | LLM Provider Adapters (OpenAI, Anthropic, Gemini, Bedrock) |
| `ANY` | `/api/orders/*` | Reverse proxied Order Service endpoints | API Key / JWT | `http://ftgo-api-gateway:8080/orders/*` |
| `ANY` | `/api/kitchen/*` | Reverse proxied Kitchen Service endpoints | API Key / JWT | `http://ftgo-api-gateway:8080/kitchen/*` |
| `ANY` | `/api/restaurants/*` | Reverse proxied Restaurant Service endpoints | API Key / JWT | `http://ftgo-api-gateway:8080/restaurants/*` |
| `ANY` | `/api/accounting/*` | Reverse proxied Accounting Service endpoints | API Key / JWT | `http://ftgo-api-gateway:8080/accounting/*` |
| `ANY` | `/api/consumers/*` | Reverse proxied Consumer Service endpoints | API Key / JWT | `http://ftgo-api-gateway:8080/consumers/*` |
| `ANY` | `/api/order-history/*` | Reverse proxied Order History Service endpoints | API Key / JWT | `http://ftgo-api-gateway:8080/order-history/*` |
| `GET` | `/health` | Gateway local liveness & readiness health probe | Public | Local FastAPI handler |
| `GET` | `/actuator/health` | Proxied downstream Spring Boot health probe | Public | `http://ftgo-api-gateway:8080/actuator/health` |

All domain API endpoints are accessed externally through this gateway at `/api/[service]/`. Do not bypass the gateway to call internal microservice ports directly in production.

---

## Kafka Events

### Edge Gateway Architecture
The Universal AI Gateway operates exclusively as a high-performance synchronous Edge HTTP/gRPC reverse proxy and router.

- **Publishes:** `N/A` (Edge gateway does not publish directly to Kafka to preserve low latency).
- **Consumes:** `N/A` (Kafka event streaming is handled downstream by microservices for Saga orchestration and CQRS replication).

---

## Database Schema

**Database:** PostgreSQL (Metadata & Audit Logs) & Redis (Rate Limiting & Semantic Cache)  
**Local Ports:** `5432` (Postgres), `6379` (Redis)

### Key PostgreSQL Tables

```sql
-- Tenants table
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    daily_cost_limit DECIMAL(10, 4) DEFAULT 100.0000,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- API Keys table
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    key_hash VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Request Logs table
CREATE TABLE request_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key_id UUID REFERENCES api_keys(id),
    tenant_id UUID REFERENCES tenants(id),
    model VARCHAR(255) NOT NULL,
    prompt_tokens INT DEFAULT 0,
    completion_tokens INT DEFAULT 0,
    total_cost DECIMAL(10, 6) DEFAULT 0.000000,
    latency_ms FLOAT NOT NULL,
    status_code INT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

---

## Local Development

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- Virtualenv setup (`.venv`)

### Run Gateway in Isolation

```bash
cd Universal-AI-Gateway

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Start FastAPI server locally
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Run via Docker Compose (Recommended)

```bash
# From repository root — brings up gateway, redis, postgres, and downstream services
docker compose up universal-ai-gateway
```

### Run Integration Tests

```bash
cd Universal-AI-Gateway

# Run full Phase 5 integration suite
.venv/Scripts/pytest tests/test_proxy.py -v

# Run with code coverage report
.venv/Scripts/pytest tests/test_proxy.py -v --cov=app.services.proxy --cov=app.core.proxy_config --cov-report=term-missing
```

---

## Kubernetes Manifests

Located in `k8s/gateway/` and `k8s/ingress/`:

| File | Purpose |
|------|---------|
| `deployment.yaml` | Pod specification, 2 replicas, CPU/memory limits, `/health` probes |
| `service.yaml` | `ClusterIP` service routing port 80 to container port 8000 |
| `configmap.yaml` | Non-sensitive configurations (`LOG_LEVEL`, `DOWNSTREAM_URL`, `CACHE_BYPASS_PATHS`) |
| `secret.yaml` | Opaque base64 secrets (`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, AWS keys) |
| `ingress.yaml` | AWS ALB Ingress controller routing external internet traffic |

### Deploy Manually

```bash
kubectl apply -f k8s/gateway/ -n ftgo
kubectl apply -f k8s/ingress/ -n ftgo
kubectl rollout status deployment/universal-ai-gateway -n ftgo
```

---

## CI/CD Pipeline

**File:** `.github/workflows/gateway.yml`

Triggers automatically on push or pull request to `main`, `dev`, or `feat/gateway` when files in `Universal-AI-Gateway/`, `k8s/gateway/`, or `k8s/ingress/` are modified.

**Pipeline Steps:**
1. Install Python dependencies (`requirements.txt` & `requirements-dev.txt`)
2. Execute automated integration test suite (`pytest tests/test_proxy.py`)
3. Build multi-arch Docker container image
4. Push image to Amazon ECR tagged with Git commit SHA
5. Roll out updated manifests to AWS EKS `ftgo` namespace

---

## Architecture Decision Record

See [`docs/adr/ADR-001-api-gateway.md`](../docs/adr/ADR-001-api-gateway.md) for full architectural design decisions — including the two-layer gateway rationale, JWT identity forwarding headers (`X-User-ID`, `X-Tenant-ID`, `X-User-Roles`), and zero-trust edge security model.

---

## Key Interview / Viva Questions

Be prepared to answer these technical questions:

1. **Why do we use a two-layer API Gateway architecture (Universal AI Gateway + FTGO API Gateway)?**
   * *Answer:* The Universal AI Gateway operates at the edge for cross-cutting security, rate limiting, LLM semantic caching, and financial budgeting. The internal FTGO API Gateway handles internal path routing and Spring Cloud microservice composition without exposing core microservices to edge vulnerabilities.

2. **How does the proxy preserve microservice database isolation?**
   * *Answer:* The gateway routes requests dynamically using HTTP headers (`X-Tenant-ID`, `X-User-ID`) without touching or sharing database connections with downstream domain microservices.

3. **Why do `/api/*` reverse proxy routes bypass semantic caching and daily USD budget checks?**
   * *Answer:* Semantic caching and daily financial budget checks are designed for expensive, non-deterministic LLM prompts (`/v1/chat/completions`). Operational CRUD microservice requests are deterministic and must never be blocked by LLM budget depletion.

4. **How are Kubernetes liveness/readiness probes handled for `/actuator/health` and `/health`?**
   * *Answer:* The gateway middleware explicitly exempts health check paths (`/health`, `/actuator/health`) from rate limiting and authentication checks to prevent Kubernetes load balancer probes from failing under high traffic.

5. **How does header handling work during request forwarding?**
   * *Answer:* Sensitive inbound credentials (`Authorization`, `X-API-Key`, `Cookie`) are stripped before forwarding downstream, while verified claims (`X-User-ID`, `X-Tenant-ID`, `X-User-Roles`, `X-Correlation-ID`) are injected into the downstream request headers.
