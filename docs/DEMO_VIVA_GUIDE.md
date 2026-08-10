# FTGO Demo & Viva Defense Guide

> **Project:** FTGO — Food-to-Go Microservices Platform  
> **Deployment:** Production-grade on AWS EKS (`ftgo-eks-cluster`, `ap-south-1`)  
> **External URL:** `http://k8s-ftgo-ftgoingr-7da04dfdb1-2025923773.ap-south-1.elb.amazonaws.com`

---

## Quick Architecture Overview

```
Internet
   │
   ▼
AWS ALB (Application Load Balancer)  ← public facing
   │
   ▼
Universal AI Gateway (FastAPI, port 8000)   ← JWT auth, rate limiting, audit logging
   │
   ▼
FTGO API Gateway (FastAPI, port 8080)        ← internal routing + API composition
   │
   ├─▶ Consumer Service   (Spring Boot, PostgreSQL)
   ├─▶ Restaurant Service (Spring Boot, PostgreSQL)
   ├─▶ Order Service      (Spring Boot, PostgreSQL + Kafka publish)
   ├─▶ Kitchen Service    (Spring Boot, PostgreSQL + Kafka consume)
   ├─▶ Accounting Service (Spring Boot, PostgreSQL + Kafka consume)
   └─▶ Order History Svc  (Spring Boot, PostgreSQL + Kafka consume — CQRS)

Shared Infrastructure
   ├─▶ Apache Kafka (KRaft mode, no Zookeeper)
   ├─▶ PostgreSQL   (Helm bitnami/postgresql)
   └─▶ Redis        (Helm bitnami/redis)
```

---

## Live Demo Commands

> Run `python demo-day-check.py` 30 minutes before demo.  
> Run `python demo-commands.py` for the live demo walk-through.

| Step | What It Shows | Command |
|------|--------------|---------|
| Health | All 4 AI providers + Redis + DB alive | `GET /health` |
| Pods | 8 microservices all Running on EKS | `kubectl get pods -n ftgo` |
| Consumer | Domain-boundary isolation | `POST /api/consumers` |
| Restaurant | Restaurant bounded context | `POST /api/restaurants` |
| Order | Saga choreography initiated | `POST /api/orders` |
| Saga | Eventual consistency in action | `GET /api/orders/{id}` |
| History | CQRS read model | `GET /api/order-history?consumerId=X` |

---

## 60-Second Viva Answers

---

### Person 1 — Order Service

> **"What does Order Service do, why is the boundary there, and one technical decision?"**

```
"Order Service owns the complete order lifecycle from creation to final
state — APPROVED or CANCELLED. The service boundary exists here because
'order management' is a distinct business capability with its own rules
and data ownership.

When a customer places an order, Order Service does NOT synchronously
call Kitchen or Accounting. Instead it saves the order as CREATED and
publishes an OrderCreated event to Kafka. Kitchen responds with
TicketCreated, Accounting with PaymentAuthorized. Only when both events
are received does Order Service move the order to APPROVED.

This is the Saga choreography pattern. The key technical decision was
using asynchronous Kafka events rather than REST calls, which means if
Accounting is down at 2am, no orders are lost — they process when
Accounting recovers. Fault isolation without distributed transactions."
```

---

### Person 2 — Kitchen & Restaurant Services

> **"What does Kitchen/Restaurant do, why the boundary, and one technical decision?"**

```
"Restaurant Service owns the menu — it's the source of truth for what
dishes are available and at what price. Kitchen Service owns kitchen
tickets — its representation of an order that needs to be prepared.

The interesting design challenge was that Kitchen needs menu data to
validate tickets, but microservices cannot share databases. We solved
this with event-driven replication: Restaurant publishes MenuUpdated
events to Kafka, and Kitchen maintains its own local read-only copy
in its own database. This makes Kitchen fully independent — it never
makes a network call to Restaurant.

The boundary between Kitchen and Restaurant exists because they have
different change rates and different owners — the kitchen operations
team vs. the menu management team — and isolating them means a menu
change never takes down the kitchen."
```

---

### Person 3 — Accounting Service

> **"What does Accounting do, why isolated, and one technical decision?"**

```
"Accounting Service handles payment authorization in complete isolation.
The boundary exists for two reasons: compliance — payment logic must
be auditable, independently deployable, and independently scalable —
and fault isolation.

When an order is placed, Accounting consumes the OrderCreated Kafka
event and asynchronously authorizes payment. If payment succeeds,
it publishes PaymentAuthorized. If it fails, PaymentFailed. Order
Service listens and compensates — it cancels the order. There is
zero synchronous coupling between Order and Accounting.

The key technical decision was using compensating transactions instead
of rollback. In a distributed system there is no global transaction
manager. Instead, each service is responsible for undoing its own
work when a failure event arrives. This is the Saga pattern's
compensation mechanism."
```

---

### Person 4 — Consumer Service & Order History (CQRS)

> **"What does Order History do, what is CQRS, and why?"**

```
"Consumer Service manages customer identity and profiles — a
straightforward bounded context.

Order History is the more architecturally interesting service. It is
a CQRS — Command Query Responsibility Segregation — read model. In
a microservices architecture, a customer's order history spans four
services: Order, Kitchen, Accounting, and Restaurant. If we queried
all four on every history request, we'd have four network calls,
fan-out complexity, and coupling between read and write paths.

Instead, Order History Service subscribes to Kafka events from all
four services and pre-computes a combined, denormalized view into its
own database. A history query is then a single fast database read —
one service, one query.

The tradeoff is eventual consistency — the view may lag by a second
or two — but for order history that is completely acceptable and
the performance benefit is significant."
```

---

### Person 5 — Universal AI Gateway & FTGO API Gateway

> **"Explain the two-layer gateway design and one bug you found."**

```
"We run a two-layer gateway. The Universal AI Gateway sits at the
network edge. It handles cross-cutting concerns: JWT authentication,
API key management, per-tenant rate limiting, and audit logging to
PostgreSQL with async S3 archival. Every single request in the system
goes through it.

Behind that, the FTGO API Gateway handles internal routing — it maps
/api/consumers to Consumer Service, /api/orders to Order Service,
and so on. It also supports API composition for aggregated views.

I extended the Universal AI Gateway — originally designed as an LLM
proxy — into a general-purpose reverse proxy for our microservices.
During integration testing I found five critical bugs. The most
interesting: Pydantic v2's BaseSettings was reading a baked .env file
from the Docker image and overwriting the Kubernetes environment
variables with localhost values, causing Redis and PostgreSQL to fail
with 'connection refused'. The fix was to add .env to .dockerignore
and switch sub-model settings to BaseModel with os.getenv() factories
that resolve at runtime, not at module import time."
```

---

## Likely Examiner Questions & Answers

### Q: "How does the system handle a payment failure?"
> Order Service receives the PaymentFailed event from Kafka → triggers compensating transaction → calls its own cancel logic → publishes OrderCancelled → Kitchen consumes OrderCancelled and deletes the ticket → Order moves to state CANCELLED. No data is left in an inconsistent state.

### Q: "Why Kafka instead of REST for service communication?"
> REST is synchronous and creates temporal coupling — if the downstream service is down, the call fails. Kafka is asynchronous and decoupled — publishers don't wait for consumers, and consumers process at their own pace. This enables fault isolation, independent scaling, and event replay.

### Q: "What happens if Kafka goes down?"
> In our current setup, Kafka runs in KRaft mode (no Zookeeper) as a single broker for demo purposes. In production, Kafka would be a 3-broker cluster with replication factor 3. If the broker is temporarily unavailable, producers retry with backoff. Events are not lost — they're persisted on disk.

### Q: "How did you handle secrets in Kubernetes?"
> All secrets are stored as Kubernetes Secrets using base64-encoded `data:` fields — never plaintext `stringData:`. Integration 3 found and removed all plaintext secrets. The next step would be Sealed Secrets or AWS Secrets Manager integration for production hardening.

### Q: "Why two gateways instead of one?"
> Separation of concerns. The Universal AI Gateway handles auth, rate limiting, and observability — concerns that apply to every service regardless of business domain. The FTGO API Gateway handles routing and composition — concerns that are specific to the FTGO business domain. This means we can evolve them independently: swap the auth provider without touching routing logic, or add a new microservice route without touching the auth layer.

### Q: "What is EKS and why use it?"
> Amazon EKS is a managed Kubernetes service. We use it because it removes the operational burden of managing the Kubernetes control plane — AWS patches, upgrades, and monitors it. Our 3-node cluster uses EC2 t3.medium worker nodes running in the ap-south-1 region. Kubernetes gives us declarative deployments, automatic pod restarts, and horizontal scaling.

### Q: "What is your CI/CD setup?"
> 7 GitHub Actions workflows, one per microservice. Each workflow triggers on push to `dev` or `main` matching the service's source path. The pipeline: runs unit tests, builds a Docker image, tags with Git SHA and `:latest`, and pushes to Amazon ECR. Kubernetes deployments always pull from ECR, so a `kubectl rollout restart` picks up the new image.

---

## Demo Day Timeline

```
T - 30 min   Run: python demo-day-check.py  ← all checks must be PASS
T - 15 min   Open: GitHub repo, architecture diagram, GitHub Actions tab
T -  5 min   Open: terminal with demo-commands.py ready
T -  0       Begin demo — Person 5 drives terminal

DEMO ORDER:
  1. Show live pods in EKS     (kubectl get pods -n ftgo)
  2. Run python demo-commands.py
  3. Show GitHub Actions green  (CI/CD pipelines)
  4. Each person: 60-second viva when called

AFTER DEMO:
  python teardown.py  ← run immediately to stop billing
  Confirm: aws eks list-clusters --region ap-south-1
```

---

## Key Numbers to Know

| Metric | Value |
|--------|-------|
| Microservices | 6 domain + 2 gateways = **8 total** |
| EKS Cluster | `ftgo-eks-cluster`, `ap-south-1`, **3 nodes** |
| Pods per service | **2 replicas** (high availability) |
| Total pods | **~16 running** |
| Issues fixed | **38 issues** documented in `docs/INTEGRATION_TROUBLESHOOTING_LOG.md` |
| E2E tests (live EKS) | **7/7 PASS** |
| CI/CD pipelines | **7 GitHub Actions workflows** |
| Integration workflows | **9/9 complete** |
| External URL | ALB on `ap-south-1` |
| Auth | JWT HS256 + tenant_id claim |
| Message broker | Apache Kafka **KRaft mode** (no Zookeeper) |
| Database | PostgreSQL (Helm bitnami) |
| Cache | Redis (Helm bitnami) |

---

*Generated by Integration 9 — Demo Prep Workflow*  
*`docs/DEMO_VIVA_GUIDE.md` — FTGO Microservices Platform*
