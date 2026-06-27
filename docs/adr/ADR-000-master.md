# ADR-000: Master Architecture Decision Record

**Date:** [Fill in final week]
**Status:** Accepted
**Owners:** All team members
**Version:** 1.0

> This document is the single source of truth for all architectural
> decisions made during the FTGO monolith-to-microservices migration.
> It is assembled from individual service ADRs in the final week of
> the project. Each section links to the detailed ADR owned by the
> responsible team member.

---

## Table of Contents

- [System Overview](#system-overview)
- [Decision 1 — Monolith Selection](#decision-1--monolith-selection)
- [Decision 2 — Decomposition Strategy](#decision-2--decomposition-strategy)
- [Decision 3 — Service Boundaries](#decision-3--service-boundaries)
- [Decision 4 — Database Per Service](#decision-4--database-per-service)
- [Decision 5 — Inter-Service Communication](#decision-5--inter-service-communication)
- [Decision 6 — API Gateway Architecture](#decision-6--api-gateway-architecture)
- [Decision 7 — Saga Pattern for Distributed Transactions](#decision-7--saga-pattern-for-distributed-transactions)
- [Decision 8 — CQRS for Order History](#decision-8--cqrs-for-order-history)
- [Decision 9 — Kubernetes Platform](#decision-9--kubernetes-platform)
- [Decision 10 — CI/CD Pipeline](#decision-10--cicd-pipeline)
- [Full Architecture Diagram](#full-architecture-diagram)
- [What We Would Do Differently](#what-we-would-do-differently)

---

## System Overview

This project migrates the FTGO (Food to Go) monolithic food delivery
application into a production-grade microservices architecture deployed
on AWS EKS. The migration follows the Strangler Fig pattern — extracting
one service at a time rather than a big-bang rewrite.

**Final system components:**

| Component | Technology | Owner |
|-----------|-----------|-------|
| Order Service | Java / Spring Boot | [Person 1] |
| Kitchen Service | Java / Spring Boot | [Person 2] |
| Restaurant Service | Java / Spring Boot | [Person 2] |
| Accounting Service | Java / Spring Boot | [Person 3] |
| Consumer Service | Java / Spring Boot | [Person 4] |
| Order History Service (CQRS) | Java / Spring Boot | [Person 4] |
| Universal AI Gateway (Edge) | Python / FastAPI | [Person 5] |
| FTGO API Gateway (Internal) | Java / Spring Cloud Gateway | [Person 5] |
| Message Broker | Apache Kafka | All |
| Databases | PostgreSQL (one per service) | Each owner |
| Orchestration | AWS EKS — ap-south-1 | [Person 5] |
| CI/CD | GitHub Actions | Each owner |

---

## Decision 1 — Monolith Selection

**Decision:** Use the FTGO application by Chris Richardson as the
monolith to decompose.

**Why:** FTGO is the companion code to *Microservices Patterns* — the
canonical industry reference for microservices decomposition. It has
enough genuine domain complexity (food ordering, kitchen management,
payment, delivery) that service boundary decisions are non-trivial and
defensible. Unlike toy applications, FTGO introduces real distributed
systems problems: shared databases, cross-domain transactions, and
read vs write model separation.

**Repos used:**
- `ftgo-monolith` — starting point (the monolith we decompose)
- `ftgo-application` — reference only (Richardson's decomposed version)

---

## Decision 2 — Decomposition Strategy

**Decision:** Use the Strangler Fig pattern — extract one service at
a time, keeping the monolith running during migration.

**Why not a big-bang rewrite:**
A full simultaneous rewrite would require all six services to be
functional before anything could be tested end-to-end. The Strangler
Fig pattern allows us to extract and validate one service at a time,
with the monolith handling everything that has not yet been extracted.
This mirrors how Netflix, Uber, and Amazon performed their own
real-world migrations.

**Extraction order:**
1. Consumer Service (simplest domain, fewest dependencies)
2. Restaurant Service (independent domain)
3. Accounting Service (isolated for compliance)
4. Kitchen Service (depends on Restaurant data via events)
5. Order Service (most complex — orchestrates the Saga)
6. Order History Service (CQRS view — depends on all other events)

**Detailed ADR:** `docs/adr/ADR-002-order-service.md` (Person 1)

---

## Decision 3 — Service Boundaries

**Decision:** Six domain services with boundaries drawn along
Domain-Driven Design (DDD) bounded contexts.

**Service boundary map:**

| Service | Owns | Does NOT own |
|---------|------|-------------|
| Order Service | `orders` table, order lifecycle, Saga orchestration | Payment, kitchen tickets, consumer profiles |
| Kitchen Service | `tickets` table, kitchen workflow | Menu data (replicates from Restaurant via events) |
| Restaurant Service | `restaurants`, `menus` tables | Order data, kitchen tickets |
| Accounting Service | `accounts`, `transactions` tables | Order data, consumer profiles |
| Consumer Service | `consumers` table, authentication | Order data |
| Order History Service | Denormalized read projection | Source-of-truth for any domain |

**The hardest boundary decisions:**

1. **Kitchen vs Restaurant:** Kitchen needs menu data to validate
   tickets, but cannot share Restaurant's database. Solution: event-
   driven replication — Restaurant publishes `MenuUpdated` events,
   Kitchen maintains its own local copy.
   See: `docs/adr/ADR-003-kitchen-restaurant.md`

2. **Order History:** Could have been a query on Order Service.
   Decision to make it a separate CQRS view was driven by the need
   to aggregate data from four services without cross-service joins.
   See: `docs/adr/ADR-005-consumer-cqrs.md`

---

## Decision 4 — Database Per Service

**Decision:** Each service owns its own PostgreSQL database. No service
reads or writes another service's database directly.

**Why:**
Shared databases are the most common failure mode of microservices
migrations — teams split the code but leave the database shared,
which preserves all the coupling they were trying to eliminate.
Database-per-service enforces true independence: each service can
be deployed, scaled, and failed independently.

**Local port assignments for development:**

| Service | DB Port |
|---------|---------|
| Order Service | 5433 |
| Kitchen Service | 5434 |
| Restaurant Service | 5435 |
| Accounting Service | 5436 |
| Consumer Service | 5437 |
| Order History Service | 5438 |

**Tradeoff accepted:** Queries that previously used SQL JOINs across
tables now require either API calls, event-driven data replication,
or CQRS views. This is the fundamental complexity cost of microservices
and is addressed explicitly in each service's ADR.

---

## Decision 5 — Inter-Service Communication

**Decision:** Asynchronous messaging via Apache Kafka for all
cross-service communication. Synchronous HTTP only for client-facing
API calls routed through the gateway.

**Why Kafka over HTTP:**

| Concern | HTTP (Sync) | Kafka (Async) |
|---------|------------|---------------|
| Temporal coupling | High — caller waits | None — fire and forget |
| Cascading failures | High — if Kitchen is down, Order fails | Low — messages queue |
| Data consistency | Requires 2-phase commit | Eventual consistency via events |
| Auditability | Requires separate logging | Topic acts as audit log |

**Kafka topic naming convention:**
`ftgo.<service>.<event>` — all lowercase, dot-separated

| Topic | Publisher | Consumers |
|-------|---------|---------|
| `ftgo.order.created` | Order Service | Kitchen, Accounting |
| `ftgo.order.cancelled` | Order Service | Kitchen, Accounting |
| `ftgo.kitchen.ticket-created` | Kitchen Service | Order Service |
| `ftgo.kitchen.ticket-rejected` | Kitchen Service | Order Service |
| `ftgo.accounting.payment-authorized` | Accounting Service | Order Service |
| `ftgo.accounting.payment-failed` | Accounting Service | Order Service |
| `ftgo.restaurant.menu-updated` | Restaurant Service | Kitchen Service |

---

## Decision 6 — API Gateway Architecture

**Decision:** Two-layer gateway architecture.
Universal AI Gateway (edge) → FTGO Spring Cloud Gateway (internal).

**Detailed ADR:** `docs/adr/ADR-001-api-gateway.md` (Person 5)

**Summary:**
- Universal AI Gateway handles: auth, rate limiting, audit logging
- FTGO Gateway handles: path routing, API composition
- This mirrors Netflix's edge/internal gateway separation

---

## Decision 7 — Saga Pattern for Distributed Transactions

**Decision:** Use the Orchestration Saga pattern for the create-order
workflow, with Order Service as the orchestrator.

**The problem:** Creating an order requires three services to
coordinate: Order Service, Kitchen Service, and Accounting Service.
In the monolith this was one database transaction. In microservices,
distributed transactions (2-phase commit) are impractical. The Saga
pattern coordinates this as a sequence of local transactions with
compensating transactions for rollback.

**Create-order Saga steps:**

```
1. Order Service    → Creates order in PENDING state
                    → Publishes OrderCreated to Kafka

2. Kitchen Service  → Consumes OrderCreated
                    → Creates kitchen ticket
                    → Publishes TicketCreated to Kafka
                    (OR TicketRejected if restaurant cannot fulfill)

3. Accounting Service → Consumes OrderCreated
                      → Authorizes payment
                      → Publishes PaymentAuthorized to Kafka
                      (OR PaymentFailed)

4. Order Service    → Consumes TicketCreated + PaymentAuthorized
                    → Confirms order — sets state to APPROVED
                    → Publishes OrderApproved to Kafka

Rollback (if any step fails):
  PaymentFailed     → Order Service cancels order
                    → Publishes OrderCancelled
                    → Kitchen Service rejects ticket on OrderCancelled
```

**Detailed ADR:** `docs/adr/ADR-002-order-service.md` (Person 1)

---

## Decision 8 — CQRS for Order History

**Decision:** Implement Order History as a separate CQRS read model
— a service that consumes events from all other services and maintains
a denormalized, read-optimized view of order history.

**The problem:** A customer viewing their order history needs data from
Order Service (status), Kitchen Service (ticket status), and Accounting
Service (payment). In the monolith this was one SQL query with JOINs.
In microservices, you cannot JOIN across service databases.

**Options rejected:**
- **API composition at the gateway:** Would require sequential HTTP calls
  per order in history — O(n) calls for a list of n orders. Unacceptable
  for large histories.
- **Order Service queries other services directly:** Creates tight coupling
  between services, defeats the purpose of separation.

**How CQRS solves it:**
Order History Service consumes events from all services and builds a
pre-computed projection. A request for order history is a single
database query on the history service's own read-optimized table.
Tradeoff: eventual consistency — the history view may be slightly
behind the source of truth.

**Detailed ADR:** `docs/adr/ADR-005-consumer-cqrs.md` (Person 4)

---

## Decision 9 — Kubernetes Platform

**Decision:** AWS EKS (Elastic Kubernetes Service) in ap-south-1
(Mumbai region). Cluster name: `ftgo-eks-cluster`. Node type: t3.medium.

**Why EKS over alternatives:**

| Option | Reason rejected / accepted |
|--------|--------------------------|
| Minikube (local) | Cannot simulate real cloud networking and load balancing |
| GKE (Google) | Team has AWS accounts — avoids additional cloud setup |
| ECS (AWS) | Not Kubernetes — doesn't satisfy course requirement |
| EKS (AWS) ✅ | Managed Kubernetes, same region as ECR, IAM integration |

**Kubernetes resource decisions:**

Every service must have:
- `Deployment` — manages pod replicas
- `Service` (ClusterIP) — internal DNS for service-to-service calls
- `ConfigMap` — non-sensitive configuration
- `Secret` — database credentials, API keys
- `livenessProbe` — Kubernetes restarts unhealthy pods
- `readinessProbe` — Kubernetes stops sending traffic to unready pods

Only the gateway has:
- `Ingress` — routes external traffic in from the load balancer

**Namespace:** All resources deployed to namespace `ftgo`

```bash
kubectl create namespace ftgo
kubectl config set-context --current --namespace=ftgo
```

---

## Decision 10 — CI/CD Pipeline

**Decision:** GitHub Actions — one workflow per service, triggered
only on changes to that service's folder.

**Why one workflow per service:**
A single monolithic pipeline would rebuild all services when any file
changes. With path filters, pushing a fix to Kitchen Service only
triggers Kitchen Service's pipeline. This mirrors how large engineering
teams handle monorepo CI/CD.

**Each workflow does:**
1. Run tests (`./gradlew test` or `pytest`)
2. Build Docker image
3. Push to Amazon ECR (tagged with Git SHA, not `latest`)
4. Apply Kubernetes manifests (`kubectl apply`)
5. Wait for rollout (`kubectl rollout status`)
6. Auto-rollback on failure (`kubectl rollout undo`)

**Path filter pattern (each person uses their own service folder):**
```yaml
on:
  push:
    paths:
      - 'ftgo-order-service/**'
      - 'k8s/order-service/**'
```

**Container registry:** Amazon ECR, same AWS account and region as EKS
(eliminates cross-region image pull latency and simplifies IAM auth via
OIDC — no long-lived credentials stored in GitHub).

---

## Full Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Internet                                  │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              AWS Load Balancer (Ingress Controller)              │
│                    ap-south-1 (Mumbai)                           │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│            Universal AI Gateway  (FastAPI / Python)              │
│  • JWT + API Key Auth      • Rate Limiting (Redis)               │
│  • Request Logging (PG)    • Audit Archive (S3)                  │
│  • Budget Enforcement      • Semantic Cache (LLM only)           │
└─────────────────────────┬───────────────────────────────────────┘
                          │  Strips: Authorization, Cookie
                          │  Adds:   X-Tenant-ID, X-User-ID
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│          FTGO API Gateway  (Spring Cloud Gateway / Java)         │
│  • Path-based Routing      • API Composition (Mono.zip)          │
│  • Distributed Tracing     • Prometheus Metrics                  │
└──────┬──────────┬──────────┬──────────┬────────────┬────────────┘
       │          │          │          │            │
       ▼          ▼          ▼          ▼            ▼
  ┌─────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐
  │ Order   │ │Kitchen │ │Restaurant│ │Accounting│ │  Consumer   │
  │ Service │ │Service │ │ Service  │ │ Service  │ │  Service    │
  │  :8081  │ │ :8082  │ │  :8083   │ │  :8084   │ │   :8085     │
  └────┬────┘ └───┬────┘ └────┬─────┘ └────┬─────┘ └──────┬──────┘
       │          │           │             │              │
       └──────────┴───────────┴──────┬──────┴──────────────┘
                                     │  Apache Kafka
                                     │  (Async Events)
                                     ▼
                          ┌──────────────────────┐
                          │  Order History Service│
                          │  (CQRS Read Model)   │
                          │       :8086           │
                          └──────────────────────┘

Each service has its own PostgreSQL database (ports 5433-5438)
All services deployed in namespace: ftgo on AWS EKS (ap-south-1)
```

---

## What We Would Do Differently

> Complete this section in the final week as a group. Be honest —
> evaluators respect reflection over perfection.

| Decision | What we did | What we'd do differently | Why |
|----------|------------|--------------------------|-----|
| [Fill in final week] | | | |
| [Fill in final week] | | | |
| [Fill in final week] | | | |

---

## Individual ADR Index

| ADR | Service | Owner | Status |
|-----|---------|-------|--------|
| [ADR-001](ADR-001-api-gateway.md) | API Gateway | [Person 5] | Accepted |
| [ADR-002](ADR-002-order-service.md) | Order Service | [Person 1] | [Status] |
| [ADR-003](ADR-003-kitchen-restaurant.md) | Kitchen + Restaurant | [Person 2] | [Status] |
| [ADR-004](ADR-004-accounting.md) | Accounting Service | [Person 3] | [Status] |
| [ADR-005](ADR-005-consumer-cqrs.md) | Consumer + Order History | [Person 4] | [Status] |
