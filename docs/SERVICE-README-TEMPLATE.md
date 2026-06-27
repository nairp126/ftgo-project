# [Service Name]

> **Owner:** [Person Name]
> **Part of:** FTGO Microservices Deployment — DevOps Course Project

---

## What This Service Does

[2-3 sentences describing the business domain this service owns.
What real-world problem does it solve? What data does it own?]

---

## Domain Responsibilities

**Owns:**
- [Table/entity 1]
- [Table/entity 2]

**Does NOT own (and never reads directly):**
- [Service boundary it respects]

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/[resource]` | [What it returns] |
| POST | `/[resource]` | [What it creates] |
| PUT | `/[resource]/{id}` | [What it updates] |

All endpoints are accessed through the API gateway at `/api/[service]/`.
Do not call this service's port directly in production.

---

## Kafka Events

### Publishes

| Topic | When | Payload |
|-------|------|---------|
| `ftgo.[service].[event]` | [When this event fires] | [Key fields] |

### Consumes

| Topic | From | Action taken |
|-------|------|-------------|
| `ftgo.[other-service].[event]` | [Publisher] | [What this service does with it] |

---

## Database Schema

**Database:** PostgreSQL
**Local port:** [5433-5438 per port table in CONTRIBUTING.md]

Key tables:

```sql
-- [Table name]
CREATE TABLE [table] (
  id          BIGSERIAL PRIMARY KEY,
  [field]     [type] NOT NULL,
  created_at  TIMESTAMP DEFAULT NOW()
);
```

---

## Local Development

### Prerequisites

- Java 17+
- Docker + Docker Compose
- The monorepo cloned and `docker compose up -d kafka` already running

### Run this service in isolation

```bash
cd [service-folder]

# Build
./gradlew build

# Run (requires Kafka and its database to be up)
./gradlew bootRun \
  --args='--spring.profiles.active=local'
```

### Run via Docker Compose (recommended)

```bash
# From repo root — starts this service and its dependencies
docker compose up [service-name]
```

### Run tests

```bash
./gradlew test

# With coverage report
./gradlew test jacocoTestReport
```

---

## Kubernetes Manifests

Located in `k8s/[service-name]/`:

| File | Purpose |
|------|---------|
| `deployment.yaml` | Pod spec, replicas, probes, resource limits |
| `service.yaml` | ClusterIP service — internal DNS |
| `configmap.yaml` | Non-sensitive config (log level, kafka broker URL) |

### Deploy manually

```bash
kubectl apply -f k8s/[service-name]/ -n ftgo
kubectl rollout status deployment/[service-name] -n ftgo
```

---

## CI/CD Pipeline

**File:** `.github/workflows/[service-name].yml`

Triggers on push to `main` or `dev` when files in
`[service-folder]/` or `k8s/[service-name]/` change.

**Steps:**
1. Run tests
2. Build Docker image
3. Push to ECR tagged with Git SHA
4. Apply Kubernetes manifests
5. Wait for rollout — auto-rollback on failure

---

## Architecture Decision Record

See [`docs/adr/ADR-00X-[service].md`](../docs/adr/ADR-00X-[service].md)
for all architectural decisions made for this service — including service
boundary justification, database ownership, and event design.

---

## Key Interview / Viva Questions

Be ready to answer these:

1. Why is [this service] a separate service and not part of [adjacent service]?
2. What database tables does this service own, and why?
3. What happens if [upstream service] is down — how does this service behave?
4. Walk me through the Kafka events this service publishes and why.
5. [Add service-specific question from CONTRIBUTING.md]
