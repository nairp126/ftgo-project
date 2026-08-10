# ADR-000: Master Architecture Decision Record

**Date:** July 2026
**Status:** Accepted
**Owners:** Kinjal Srivastava, Vikrant Rana, Anirudh Chawla, Anshuman Rangarh, Pranav Nair
**Version:** 2.0 (Final)

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
- [Decision 11 — Kafka KRaft Mode](#decision-11--kafka-kraft-mode)
- [Decision 12 — EKS Teardown and Redeploy Strategy](#decision-12--eks-teardown-and-redeploy-strategy)
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
| Order Service | Java / Spring Boot | Kinjal Srivastava |
| Kitchen Service | Java / Spring Boot | Vikrant Rana |
| Restaurant Service | Java / Spring Boot | Vikrant Rana |
| Accounting Service | Java / Spring Boot | Anirudh Chawla |
| Consumer Service | Java / Spring Boot | Anshuman Rangarh |
| Order History Service (CQRS) | Java / Spring Boot | Anshuman Rangarh |
| Universal AI Gateway (Edge) | Python / FastAPI | Pranav Nair |
| FTGO API Gateway (Internal) | Python / FastAPI | Pranav Nair |
| Message Broker | Apache Kafka (KRaft mode) | Pranav Nair |
| Databases | PostgreSQL (one per service) | Each owner |
| Orchestration | AWS EKS — ap-south-1 | Pranav Nair |
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

## Decision 11 — Kafka KRaft Mode (No Zookeeper)

**Decision:** Deploy Apache Kafka in KRaft mode (`confluentinc/cp-kafka:7.5.0`)
with `KAFKA_PROCESS_ROLES: broker,controller` — single-node, no Zookeeper.

**Why:**
Zookeeper was deprecated in Kafka 3.x and removed in 4.0. KRaft mode
eliminates the external dependency, simplifying the deployment from two
pods (Kafka + Zookeeper) to one. For a course project with a single
broker topology this is the correct choice.

**Critical configuration found in production:**
```yaml
spec:
  template:
    spec:
      enableServiceLinks: false  # REQUIRED
```
Without `enableServiceLinks: false`, Kubernetes injects `KAFKA_PORT=tcp://...`
into the pod. Confluent's entrypoint maps all `KAFKA_*` env vars to
`server.properties`, causing `port=tcp://...` which crashes Kafka.
This was Issue 10 in the troubleshooting log.

**Alternatives considered:**
- Strimzi Operator: Better for production, too heavyweight for this project scope.
- Zookeeper mode: Deprecated, requires an additional deployment.

---

## Decision 12 — EKS Teardown and Redeploy Strategy

**Decision:** Complete teardown via `teardown.py` (7-step sequence);
redeploy via EKS Deployment Guide §6…14 (one-time setup in §1–5 persists).

**Why a custom teardown script:**
`eksctl delete cluster` alone is insufficient. It does not:
- Clean up the ALB (created by the Load Balancer Controller from an Ingress
  resource — must be removed *before* the cluster is deleted, by deleting
  the `ftgo` namespace first and waiting for LBC to deregister the ALB).
- Delete manually-created IAM roles (`AmazonEKSLoadBalancerControllerRole`,
  `AmazonEKS_EBS_CSI_DriverRole`) or IAM policies.
- Delete the cluster OIDC provider.

**Teardown sequence (enforced order):**
1. Delete `ftgo` namespace → triggers LBC to deprovision ALB
2. Poll until ALB is gone (max 90s)
3. `eksctl delete cluster --wait` → CloudFormation stacks
4. Delete IAM roles (detach policies first)
5. Delete IAM policy (`AWSLoadBalancerControllerIAMPolicy`)
6. Delete OIDC provider
7. Optionally delete ECR repos (default: retain for fast redeploy)

**What survives teardown (by design):**
- ECR repositories + all 8 service images (S3-tier storage cost only)
- GitHub repository + all manifests + CI/CD workflows
- GitHub Secrets (AWS credentials, EKS cluster name)
- GitHub OIDC provider in AWS IAM (`token.actions.githubusercontent.com`)

**Redeploy time after teardown:** ~40…45 minutes (cluster creation + infrastructure).
Image builds are skipped because ECR already has images from CI/CD.

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
│          FTGO API Gateway  (FastAPI / Python)                    │
│  • Path-based Routing      • Request Proxying                    │
│  • Service Discovery       • Health Aggregation                  │
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
| Secret management | Hard-coded base64 secrets in `secret.yaml` committed to repo | Use AWS Secrets Manager or HashiCorp Vault with external-secrets-operator | Committed secrets are a security risk even when base64-encoded — not true encryption |
| Single Kafka broker | One KRaft broker, no replication | Use at least 3 brokers with replication factor 3 | Single broker is a SPOF; any crash loses all in-flight messages |
| Database isolation | One shared PostgreSQL instance, separate databases per service | One RDS instance per service or use Aurora Serverless | Shared instance creates noisy-neighbour risk; one service can exhaust connections |
| CI/CD depth | Push-to-ECR only for most services; `kubectl apply` only in gateway workflow | Add `kubectl rollout status` + auto-rollback (`kubectl rollout undo`) to all pipelines | Most pipelines do not verify the deployment succeeded after push |
| Observability | Actuator health endpoints only | Add Prometheus + Grafana + distributed tracing (Jaeger/Zipkin) to EKS | Without metrics dashboards, debugging production issues is entirely log-based |

---

## Individual ADR Index

| ADR | Service | Owner | Status |
|-----|---------|-------|--------|
| [ADR-001](ADR-001-api-gateway.md) | Universal AI Gateway + FTGO API Gateway | Pranav Nair | Accepted |
| [ADR-002](ADR-002-order-service.md) | Order Service | Kinjal Srivastava | Accepted |
| [ADR-003](ADR-003-kitchen-restaurant.md) | Kitchen + Restaurant Services | Vikrant Rana | Accepted |
| [ADR-004](ADR-004-accounting-service.md) | Accounting Service | Anirudh Chawla | Accepted |
| [ADR-005](ADR-005-consumer-cqrs.md) | Consumer + Order History Services | Anshuman Rangarh | Accepted |
