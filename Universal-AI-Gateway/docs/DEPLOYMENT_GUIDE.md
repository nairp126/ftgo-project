# 🚢 Deployment Guide

Guidelines for deploying the Universal LLM Gateway to production environments.

---

## ⚡ Quickstart (Local / Development)

The fastest way to get running is using the **bootstrap script**, which sets up your `.env`, starts all Docker services, and runs database migrations automatically.

```bash
# Linux / macOS
bash scripts/bootstrap.sh

# Windows (PowerShell)
.\scripts\bootstrap.ps1
```

**What the bootstrap does**:
1. Copies `.env.example` → `.env` (if missing).
2. Optionally prompts for OpenAI / Anthropic API keys.
3. Runs `docker-compose up -d --build`.
4. Waits for PostgreSQL healthcheck, then runs `alembic upgrade head`.

**Service URLs after bootstrap**:

| Service | URL |
| :--- | :--- |
| Gateway API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |
| Prometheus Metrics | http://localhost:8000/metrics |
| Jaeger Tracing UI | http://localhost:16686 |

---

## 🐳 Docker Compose Architecture

The `docker-compose.yml` spins up four services:

| Service | Image | Port | Role |
| :--- | :--- | :--- | :--- |
| `postgres` | `postgres:15-alpine` | `5432` | Persistent storage for tenants, API keys, request logs |
| `redis` | `redis/redis-stack-server:latest` | `6379` | Rate limiting, caching, budget tracking, circuit breakers |
| `jaeger` | `jaegertracing/all-in-one:latest` | `16686` (UI), `4417` (OTLP) | Distributed tracing (OpenTelemetry) |
| `gateway` | Built from `Dockerfile` | `8000` | The LLM Gateway application |

> [!IMPORTANT]
> Redis uses the **redis-stack-server** image (not plain Redis) to enable **RediSearch** vector similarity search for semantic caching.

### Manual Docker Compose

```bash
# Start all services
docker-compose up -d

# View gateway logs
docker-compose logs -f gateway

# Run database migrations manually
docker-compose exec gateway alembic upgrade head
```

---

## 📦 Container Build

The `Dockerfile` uses a **multi-stage build** and runs as a non-root user (`appuser`) for security.

```bash
docker build -t llm-gateway:latest .
```

**Resource Recommendations**:
- **CPU**: 1–2 vCPU per instance.
- **Memory**: 2 GB minimum (4 GB recommended if semantic caching is enabled).

---

## ⚙️ Environment Configuration

Copy the template and fill in your secrets:

```bash
cp .env.example .env
```

**Critical variables to set** (all others have safe defaults):

| Variable | Description |
| :--- | :--- |
| `OPENAI_API_KEY` | OpenAI provider key |
| `ANTHROPIC_API_KEY` | Anthropic provider key |
| `GOOGLE_API_KEY` | Google Gemini provider key |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | AWS Bedrock credentials |
| `DB_PASSWORD` | PostgreSQL password |
| `ADMIN_API_KEY` | Gateway admin secret |
| `WEBHOOK_URL` | Slack / webhook URL for budget alerts |
| `MOCK_LLM` | Set `true` in dev to avoid real API calls |
| `ENABLE_TRACING` | Set `false` to disable OpenTelemetry |

---

## ☸️ Kubernetes Deployment

### Helm Chart (Recommended)

A production-ready Helm chart is in the `charts/` directory:

```bash
# Install
helm install universal-gateway ./charts/gateway

# Upgrade
helm upgrade universal-gateway ./charts/gateway

# Dry-run / lint validation
helm lint ./charts/gateway
helm install --dry-run universal-gateway ./charts/gateway
```

### Core Kubernetes Components

- **Deployment**: Horizontally scalable, stateless gateway pods.
- **Service**: Internal ClusterIP load balancing.
- **Ingress**: TLS termination and external routing.
- **HPA**: Horizontal Pod Autoscaler for load-based scaling.
- **NetworkPolicy**: Restricts inter-pod traffic.
- **ConfigMap**: Non-sensitive environment variables.
- **Secret**: API keys and database credentials.

### Manifest-Based (Legacy)

```bash
kubectl apply -f k8s/
```

---

## 🔄 Horizontal Scaling

The gateway is **stateless** (state lives in Redis + PostgreSQL). Scale replicas freely:

```bash
kubectl autoscale deployment gateway --cpu-percent=70 --min=2 --max=10
```

---

## 🛡️ Production Hardening Checklist

1. [ ] **SSL/TLS**: Ensure Ingress or ALB terminates SSL — never expose port 8000 directly.
2. [ ] **Database**: Use a managed Postgres service (e.g., AWS RDS) with automated backups.
3. [ ] **Redis**: Use a managed Redis service (e.g., AWS ElastiCache) with Redis Stack / RedisSearch module.
4. [ ] **Secrets**: Rotate `ADMIN_API_KEY` and all LLM provider keys before go-live. Ensure `.env` matches `.env.example` structure.
5. [ ] **Tracing**: Set `ENABLE_TRACING=true` and point `OTLP_ENDPOINT` to your tracing backend.
6. [ ] **Webhooks**: Set `WEBHOOK_URL` to receive budget and circuit breaker alerts.
7. [ ] **Observability**: Import `grafana-dashboard.json` into your Grafana instance.
8. [ ] **PII Redaction**: Confirm `LOG_PII_REDACTION=true` for compliance workloads.
