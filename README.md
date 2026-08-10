# Containerized Microservices Deployment on Kubernetes

> **Course Project — DevOps**
> Breaking a monolithic food delivery application into microservices,
> containerized with Docker and orchestrated on AWS EKS (Kubernetes).

---

## Table of Contents

- [Project Overview](#project-overview)
- [Team](#team)
- [Architecture](#architecture)
- [Repository Structure](#repository-structure)
- [Quick Start](#quick-start)
- [Documentation Index](#documentation-index)
- [Deployment](#deployment)
- [Technology Stack](#technology-stack)

---

## Project Overview

This project migrates the **FTGO (Food to Go)** monolithic food delivery
application into a microservices architecture. The original monolith is
available at
[microservices-patterns/ftgo-monolith](https://github.com/microservices-patterns/ftgo-monolith)
and is the companion code to *Microservices Patterns* by Chris Richardson.

The final system consists of six domain microservices, a two-layer API
gateway, asynchronous messaging via Apache Kafka, and a full CI/CD pipeline
deploying to AWS EKS in the `ap-south-1` (Mumbai) region.

### What we built

| Component | Technology | Owner | GitHub |
|-----------|-----------|-------|--------|
| Order Service | Java / Spring Boot | Kinjal Srivastava | [@kinjalsrivastava](https://github.com/kinjalsrivastava) |
| Kitchen Service | Java / Spring Boot | Vikrant Rana | [@vikrantrana](https://github.com/vikrantrana) |
| Restaurant Service | Java / Spring Boot | Vikrant Rana | [@vikrantrana](https://github.com/vikrantrana) |
| Accounting Service | Java / Spring Boot | Anirudh Chawla | [@anirudhchawla](https://github.com/anirudhchawla) |
| Consumer Service | Java / Spring Boot | Anshuman Rangarh | [@EfxAnsh](https://github.com/EfxAnsh) |
| Order History Service | Java / Spring Boot | Anshuman Rangarh | [@EfxAnsh](https://github.com/EfxAnsh) |
| Universal AI Gateway (Edge) | Python / FastAPI | Pranav Nair | [@nairp126](https://github.com/nairp126) |
| FTGO API Gateway (Internal) | Java / Spring Cloud Gateway | Pranav Nair | [@nairp126](https://github.com/nairp126) |
| Kubernetes Platform | AWS EKS | All | - |
| CI/CD Pipelines | GitHub Actions | Each person | - |

---

## Team

| Name | Role | Services Owned | GitHub |
|------|------|---------------|--------|
| Kinjal Srivastava | Order Service Lead | Order Service | [@kinjalsrivastava](https://github.com/kinjalsrivastava) |
| Vikrant Rana | Kitchen Lead | Kitchen Service, Restaurant Service | [@vikrantrana](https://github.com/vikrantrana) |
| Anirudh Chawla | Accounting Lead | Accounting Service | [@anirudhchawla](https://github.com/anirudhchawla) |
| Anshuman Rangarh | Consumer Lead | Consumer Service, Order History Service | [@EfxAnsh](https://github.com/EfxAnsh) |
| Pranav Nair | Platform & Gateway Lead | Universal AI Gateway, FTGO API Gateway, Kubernetes Platform | [@nairp126](https://github.com/nairp126) |

---

## Architecture

```
Internet
    │
    ▼
[AWS Load Balancer Ingress]
    │
    ▼
[Universal AI Gateway — FastAPI/Python]        ← Edge Layer
  · JWT + API Key Authentication
  · Per-tenant Rate Limiting (Redis)
  · Request Logging (PostgreSQL)
  · Audit Archiving (S3)
  · Semantic Caching (LLM routes only)
  · Budget Enforcement (LLM routes only)
    │
    ▼
[FTGO API Gateway — Spring Cloud Gateway]      ← Internal Routing Layer
  · Path-based Routing
  · API Composition (fan-out)
  · Distributed Tracing (Sleuth + Zipkin)
  · Prometheus Metrics
    │
    ├──▶ Order Service         :8080
    ├──▶ Kitchen Service       :8080
    ├──▶ Restaurant Service    :8080
    ├──▶ Accounting Service    :8080
    ├──▶ Consumer Service      :8080
    └──▶ Order History Service :8080
```

All inter-service communication is **asynchronous via Apache Kafka**.
Each service owns its own PostgreSQL database — no shared databases.

---

## Repository Structure

```
ftgo-devops-project/
│
├── ftgo-monolith/                        # Reference only — do not modify
│
├── ftgo-order-service/                   # Person 1
├── ftgo-kitchen-service/                 # Person 2
├── ftgo-restaurant-service/              # Person 2
├── ftgo-accounting-service/              # Person 3
├── ftgo-consumer-service/                # Person 4
├── ftgo-order-history-service/           # Person 4
│
├── universal-ai-gateway/                 # Person 5
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── routes.py
│   │   │   ├── health.py
│   │   │   └── admin.py
│   │   ├── core/
│   │   │   ├── proxy_config.py           # NEW — route table
│   │   │   ├── jwt_handler.py            # NEW — JWT validation
│   │   │   └── config.py
│   │   ├── services/
│   │   │   ├── proxy.py                  # NEW — reverse proxy handler
│   │   │   └── router.py
│   │   ├── middleware/
│   │   │   ├── auth.py
│   │   │   └── rate_limit.py
│   │   └── cache/
│   │       └── cache_manager.py
│   ├── tests/
│   │   └── test_proxy.py                 # NEW — integration tests
│   ├── Dockerfile
│   └── requirements.txt
│
├── k8s/                                  # Kubernetes manifests
│   ├── gateway/                          # Person 5
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml
│   │   ├── secret.yaml
│   │   └── ingress.yaml
│   ├── order-service/                    # Person 1
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── configmap.yaml
│   ├── kitchen-service/                  # Person 2
│   ├── restaurant-service/               # Person 2
│   ├── accounting-service/               # Person 3
│   ├── consumer-service/                 # Person 4
│   ├── order-history-service/            # Person 4
│   ├── kafka/                            # All together — Week 5
│   │   └── kafka.yaml
│   └── ingress/                          # Person 5
│       └── ingress-controller.yaml
│
├── docs/
│   ├── adr/
│   │   ├── ADR-TEMPLATE.md
│   │   ├── ADR-000-master.md             # Final week — all together
│   │   ├── ADR-001-api-gateway.md        # Person 5
│   │   ├── ADR-002-order-service.md      # Person 1
│   │   ├── ADR-003-kitchen-restaurant.md # Person 2
│   │   ├── ADR-004-accounting.md         # Person 3
│   │   └── ADR-005-consumer-cqrs.md      # Person 4
│   ├── architecture-diagram.png          # All together — Week 3
│   ├── pre-migration-checklist.md
│   └── runbook.md                        # Person 5
│
├── .github/
│   └── workflows/
│       ├── gateway.yml                   # Person 5
│       ├── order-service.yml             # Person 1
│       ├── kitchen-service.yml           # Person 2
│       ├── restaurant-service.yml        # Person 2
│       ├── accounting-service.yml        # Person 3
│       ├── consumer-service.yml          # Person 4
│       └── order-history-service.yml     # Person 4
│
├── docker-compose.yml                    # Local dev — all services
├── docker-compose.override.yml           # Local port/volume overrides
├── CONTRIBUTING.md
└── README.md
```

---

## Quick Start

For full AWS EKS deployment, see [`docs/EKS_DEPLOYMENT_GUIDE.md`](docs/EKS_DEPLOYMENT_GUIDE.md).

For local development:

```bash
# Clone the repo
git clone https://github.com/nairp126/ftgo-project.git
cd ftgo-project

# Start all services locally
docker compose up --build

# Verify gateway is up
curl http://localhost:8000/health
```

---

## Documentation Index

| Document | Purpose |
|----------|---------|
| [`docs/EKS_DEPLOYMENT_GUIDE.md`](docs/EKS_DEPLOYMENT_GUIDE.md) | **Primary deployment reference** — first-time setup AND redeploy after teardown |
| [`docs/INTEGRATION_TROUBLESHOOTING_LOG.md`](docs/INTEGRATION_TROUBLESHOOTING_LOG.md) | All 43 issues encountered during deployment with root cause and fix |
| [`docs/DEPLOYMENT_ERRORS.md`](docs/DEPLOYMENT_ERRORS.md) | CI/CD and Kubernetes error reference (17 categorised issues) |
| [`docs/DEMO_VIVA_GUIDE.md`](docs/DEMO_VIVA_GUIDE.md) | Viva defence guide — 60s answers, examiner Q&A for all 5 roles |
| [`docs/adr/ADR-000-master.md`](docs/adr/ADR-000-master.md) | Master ADR — all 12 architectural decisions with rationale |
| [`docs/adr/ADR-001-api-gateway.md`](docs/adr/ADR-001-api-gateway.md) | Gateway architecture decisions (Pranav Nair) |
| [`docs/adr/ADR-002-order-service.md`](docs/adr/ADR-002-order-service.md) | Order Service decisions (Kinjal Srivastava) |
| [`docs/adr/ADR-003-kitchen-restaurant.md`](docs/adr/ADR-003-kitchen-restaurant.md) | Kitchen + Restaurant decisions (Vikrant Rana) |
| [`docs/adr/ADR-004-accounting-service.md`](docs/adr/ADR-004-accounting-service.md) | Accounting Service decisions (Anirudh Chawla) |
| [`docs/adr/ADR-005-consumer-cqrs.md`](docs/adr/ADR-005-consumer-cqrs.md) | Consumer + CQRS decisions (Anshuman Rangarh) |
| [`docs/pre-migration-checklist.md`](docs/pre-migration-checklist.md) | Everything to verify before starting migration |
| [`docs/runbook.md`](docs/runbook.md) | Original local dev runbook |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Branch strategy, PR rules, commit conventions |

---

## Deployment

Full deployment instructions in [`docs/EKS_DEPLOYMENT_GUIDE.md`](docs/EKS_DEPLOYMENT_GUIDE.md).

**Cluster:** `ftgo-eks-cluster` — AWS EKS, region `ap-south-1` (Mumbai)
**Registry:** Amazon ECR (`120569617989.dkr.ecr.ap-south-1.amazonaws.com`)
**CI/CD:** GitHub Actions — each service has its own workflow under `.github/workflows/`
**Teardown:** `python teardown.py` — destroys all AWS resources safely after demo

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Language (Services) | Java 17 |
| Framework (Services) | Spring Boot 3, Spring Cloud |
| Language (Gateway) | Python 3.12 |
| Framework (Gateway) | FastAPI |
| Messaging | Apache Kafka |
| Databases | PostgreSQL (one per service) |
| Caching | Redis |
| Container Runtime | Docker |
| Orchestration | Kubernetes (AWS EKS) |
| Service Mesh / Tracing | Spring Cloud Sleuth + Zipkin |
| Metrics | Prometheus + Micrometer |
| CI/CD | GitHub Actions |
| Container Registry | Amazon ECR |
| Cloud | AWS (ap-south-1) |
