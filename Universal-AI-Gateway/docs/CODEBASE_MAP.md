# 🗺️ Codebase Map

A technical directory of the Universal LLM Gateway codebase to assist developers in navigating the architecture and implementation details.

## 📂 `app/` - Core Application Logic

| File/Directory | Responsibility | Technical Implementation |
| :--- | :--- | :--- |
| `main.py` | App Entrypoint | FastAPI application factory, middleware wiring. |
| `api/` | Route Handlers | `/v1/chat/completions`, `/health`, `/admin` endpoints. |
| `middleware/` | Ingress Filters | Auth, Rate Limiting, Security Headers, Error Handling. |
| `services/` | Business Logic | Router, Ensembler, Budget Manager, PII Redactor, **Notifier**. |
| `providers/` | Adapter Layer | OpenAI, Anthropic, **Gemini**, Bedrock adapters; Circuit Breaker. |
| `cache/` | Caching Logic | Redis exact-match and RediSearch semantic caching. |
| `db/` | Persistence | SQLAlchemy models and database connection manager. |
| `schemas/` | Validation | Pydantic models for request/response validation. |
| `core/` | Infrastructure | Configuration (Pydantic Settings), Logging, Security. |

---

## 📂 `tests/` - Quality Assurance

| File/Pattern | Category | Description |
| :--- | :--- | :--- |
| `test_api.py` / `test_integration.py` / `test_http_integration.py` | Integration | End-to-end API lifecycle and request routing integration testing. |
| `test_auth.py` / `test_security.py` | Security | API key validation, Argon2id verification, and security headers. |
| `test_providers.py` | Unit | Comprehensive adapter and circuit breaker tests for each LLM provider. |
| `test_cache.py` / `test_rate_limiter.py` / `test_budget_manager.py` | Unit | Tests for enterprise features: semantic/exact cache, rate limiting, and daily budget tracking. |
| `test_router.py` / `test_ensembler.py` / `test_safety_filter.py` | Unit | Core routing engine, model race mode ensembler, and regex safety checks. |
| `test_properties_cache.py` / `test_properties_providers.py` | Property-based | Hypothesis-based testing for cache validity and provider response robustness. |
| `conftest.py` | Fixtures | Shared test dependencies, database mocks, and provider client configurations. |
| `scripts/e2e_test_requests.py` | E2E | CLI utility for running end-to-end request test scenarios. |


---

## 📂 `root/` - Infrastructure & Governance

| File/Directory | Purpose |
| :--- | :--- |
| `Dockerfile` | Multi-stage build for production-ready containerization. |
| `docker-compose.yml` | Local orchestration (Gateway, Postgres, Redis, RediSearch). |
| `alembic.ini` | Database migration configuration. |
| `requirements.txt` | Core application dependencies. |
| `run.py` | Development server startup script. |
| `LICENSE` | Apache License 2.0. |
| `CODE_OF_CONDUCT.md` | Community standards and ethical guidelines. |
| `CONTRIBUTING.md` | Setup and pull request instructions for developers. |
| `docs/` | Comprehensive technical documentation hub. |
| `k8s/` | Kubernetes manifests for production deployment. |
| `monitoring/` | Monitoring configurations (OpenTelemetry, metrics). |
| `scripts/` | Admin Tools & Bootstrap scripts (Requirements 13.5, 15.2). |
| `charts/` | Helm Chart for Kubernetes deployment (Requirements 18.2). |
| `migrations/` | Database version control (Alembic). |
