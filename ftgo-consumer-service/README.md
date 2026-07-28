# Consumer Service

> **Owner:** Anshuman Rangarh
> **Part of:** FTGO Microservices Deployment — DevOps Course Project

---

## What This Service Does

The Consumer Service is responsible for managing consumer profiles.
It handles user registration and maintains essential consumer data.

---

## Domain Responsibilities

**Owns:**
- Consumer
- PersonName

**Does NOT own (and never reads directly):**
- Orders
- Payment details

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/consumers/{id}` | Gets consumer details |
| POST | `/consumers` | Creates a new consumer |

All endpoints are accessed through the API gateway at `/consumers`.
Do not call this service's port directly in production.

---

## Kafka Events

### Publishes

| Topic | When | Payload |
|-------|------|---------|

### Consumes

| Topic | From | Action taken |
|-------|------|-------------|
| `payment.authorized` | Accounting | Updates consumer or processes payment authorization |
| `payment.failed` | Accounting | Handles payment failure |
| `ticket.created` | Kitchen | Processes ticket creation |
| `ticket.rejected` | Kitchen | Processes ticket rejection |
| `order.created` | Order | Processes order creation |

---

## Database Schema

**Database:** PostgreSQL
**Local port:** 5432

Key tables:

```sql
CREATE TABLE consumer (
  id          BIGSERIAL PRIMARY KEY,
  first_name  VARCHAR(255) NOT NULL,
  last_name   VARCHAR(255) NOT NULL
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
cd ftgo-consumer-service

# Build
./mvnw clean package -DskipTests

# Run (requires Kafka and its database to be up)
./mvnw spring-boot:run \
  -Dspring-boot.run.profiles=local
```

### Run via Docker Compose (recommended)

```bash
# From repo root — starts this service and its dependencies
docker compose up consumer-service
```

---

## Kubernetes Manifests

Located in `k8s/`:

| File | Purpose |
|------|---------|
| `deployment.yaml` | Pod spec, replicas, probes, resource limits |
| `service.yaml` | ClusterIP service — internal DNS |

### Deploy manually

```bash
kubectl apply -f k8s/ -n ftgo
kubectl rollout status deployment/consumer-service -n ftgo
```
