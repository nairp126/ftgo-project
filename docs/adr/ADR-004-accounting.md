# ADR-004: Accounting Service — Bounded Context, PCI Isolation, and Saga Participation

| Field       | Value                                      |
|-------------|--------------------------------------------|
| **Status**  | Accepted                                   |
| **Date**    | 2024-01-15                                 |
| **Authors** | Person 3 (Accounting Service Owner)        |
| **Deciders**| All Persons (architectural review)         |
| **Tags**    | microservices, saga, pci-compliance, kafka |

---

## Context

The FTGO (Food To Go) system is a Kubernetes-deployed microservices architecture modelled on the classic reference implementation described in _Microservices Patterns_ (Chris Richardson). When a consumer places an order, the system must:

1. Validate the order structure (Order Service).
2. **Authorize payment** before committing to fulfilment.
3. Create a kitchen ticket (Kitchen Service).
4. Deliver the order (Delivery Service, out of scope here).

The question this ADR answers is: **why should payment authorization logic live in its own bounded context (the Accounting Service) rather than inside the Order Service or a shared module?**

There are two independent drivers:

### Driver 1 — Domain Separation
Payment and accounting logic represents a distinct bounded context with its own ubiquitous language (`ConsumerAccount`, `PaymentAuthorization`, `CreditHold`, `Reversal`). Embedding this inside Order Service would create a _Big Ball of Mud_ — a single service responsible for order lifecycle management *and* financial record-keeping, violating the Single Responsibility Principle at the service level.

### Driver 2 — PCI DSS Compliance Scope Reduction
Any service that **processes, stores, or transmits cardholder data** (or data that can directly affect cardholder accounts) falls within the **PCI DSS audit scope**. The larger the scope, the more expensive, complex, and risky compliance becomes.

By isolating all payment-handling code, data models, and operational access in a single dedicated service, we achieve:
- **Minimal PCI scope**: Only the Accounting Service and its database are audited. No other FTGO service touches cardholder-adjacent data.
- **Network segmentation**: Kubernetes `NetworkPolicy` can restrict pod-to-pod communication so that only authorised services send commands to Accounting Service.
- **Access control boundary**: Only the Accounting Service's service account has credentials to its Postgres schema. Engineers supporting Order or Kitchen services cannot accidentally (or deliberately) query payment records.
- **Audit log concentration**: All payment-related mutations flow through a single code path, making audit trails complete and tamper-evident.

---

## Decision

**The Accounting Service is its own independently deployable microservice with a dedicated Postgres schema (database-per-service pattern). No other FTGO service may read from or write to its tables directly.**

The Accounting Service:
- Owns the `consumer_accounts` and `payment_authorizations` tables exclusively.
- Communicates with the rest of the system exclusively via Kafka events (asynchronous messaging) — no synchronous HTTP calls that would create tight coupling.
- Participates in the create-order Saga as a **participant** (not the orchestrator).

---

## PCI DSS Compliance Rationale

> _"The goal of PCI DSS is to protect cardholder data wherever it is processed, stored, or transmitted."_ — PCI DSS v4.0

### How isolation reduces PCI scope

| Without Isolation | With Accounting Service |
|---|---|
| Order Service handles payment → entire Order Service DB, code, CI/CD, and team access are in PCI scope | Only Accounting Service is in scope |
| Kitchen Service reads shared DB → Kitchen infra enters scope | Kitchen Service never touches payment data |
| Broad access control needed across many teams | Single service account, one Postgres schema, isolated Kubernetes namespace |
| Any bug in any service can potentially expose payment data | Blast radius limited to Accounting Service |

### What we do NOT store
Real card numbers (PANs), CVVs, and magnetic stripe data are **never** stored in this service. In a production deployment, Accounting Service would call a PCI-certified vault (e.g. Stripe, Braintree) to tokenise card data. The service stores only the **result** of an authorization (status, amount, timestamp) and a payment provider token — not the raw card data itself.

This means even if the `payment_authorizations` table is breached, no cardholder data is exposed — only authorization outcomes.

---

## Saga Participation

### The Create-Order Saga

The Accounting Service is a **Saga participant** (not the orchestrator). The Order Service acts as the orchestrator.

```
┌─────────────────────────────────────────────────────────────────┐
│                   Create-Order Saga                             │
│                   (Orchestrator: Order Service)                 │
└─────────────────────────────────────────────────────────────────┘

Step 1: Order Service creates pending order record
        │
        └──► publishes [order.created] ──────────────────────────►┐
                                                                   │
Step 2: Accounting Service (this service)                          │
        │◄──────────────────────────────────────────────────────── ┘
        │  - Looks up consumer account
        │  - Checks available credit
        │  - Places a hold (deducts credit)
        │  - Persists PaymentAuthorization record
        │
        ├─── SUCCESS ──► publishes [payment.authorized] ──────────►┐
        │                                                           │
        └─── FAILURE ──► publishes [payment.failed] ─────────────►┐│
                                                                   ││
Step 3: Order Service receives result                             ││
        ├─── payment.authorized ──► proceed to kitchen step ◄─────┘│
        └─── payment.failed ──► abort Saga ◄──────────────────────┘
```

---

## Consequences

### Positive
- Services evolve independently.
- Failures are isolated.
- Clear service ownership.

### Negative
- Eventual consistency requires careful monitoring.
