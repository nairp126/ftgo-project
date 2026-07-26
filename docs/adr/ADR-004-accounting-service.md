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

### What Accounting Service does on `OrderCreated`

1. **Idempotency check** — query `payment_authorizations` for `orderId`. If found, replay existing result (see below). This prevents double-charging on Kafka at-least-once redelivery.
2. **Account lookup** — fetch `ConsumerAccount` by `consumerId`.
3. **Authorization attempt** — call `ConsumerAccount.authorize(orderTotal)`. This is a simple credit-hold: if `availableCredit >= orderTotal`, deduct and return `true`; otherwise return `false`.
4. **Persist** — save `PaymentAuthorization` record with status `AUTHORIZED` or `DECLINED`.
5. **Publish** — emit `payment.authorized` or `payment.failed` to Kafka.

### Compensating Transaction (Saga Rollback)

If a **later** Saga step fails (e.g. Kitchen Service rejects the ticket because an item is unavailable), the Order Service must roll back previously completed steps. For the Accounting Service this means:

1. Order Service publishes a `CancelPaymentAuthorization` command (or a dedicated compensation event).
2. Accounting Service consumes it and calls `reverseAuthorization(orderId)`:
   - Sets `PaymentAuthorization.status = REVERSED`
   - Calls `ConsumerAccount.releaseAuthorization(amount)` to restore the credit hold

This is the classic Saga compensating transaction — it does not use database transactions that span service boundaries (which would require 2PC and violate microservice principles). Instead, each service implements its own undo operation.

---

## Events Consumed

| Topic | Event | Trigger |
|---|---|---|
| `order.created` | `OrderCreatedEvent` | A new order was placed by the Order Service Saga orchestrator |

**`OrderCreatedEvent` schema:**
```json
{
  "orderId":    12345,
  "consumerId": 67890,
  "orderTotal": 49.99
}
```

## Events Published

| Topic | Event | Condition |
|---|---|---|
| `payment.authorized` | `PaymentAuthorizedEvent` | Authorization succeeded (sufficient credit) |
| `payment.failed` | `PaymentFailedEvent` | Authorization declined (insufficient funds or account not found) |

**`PaymentAuthorizedEvent` schema:**
```json
{
  "orderId":          12345,
  "consumerId":       67890,
  "authorizedAmount": 49.99,
  "authorizedAt":     "2024-01-15T10:30:00Z"
}
```

**`PaymentFailedEvent` schema:**
```json
{
  "orderId":    12345,
  "consumerId": 67890,
  "amount":     49.99,
  "reason":     "INSUFFICIENT_FUNDS",
  "failedAt":   "2024-01-15T10:30:01Z"
}
```

---

## Idempotency Design

Kafka guarantees **at-least-once** delivery. This means the Accounting Service may receive the same `OrderCreated` event multiple times (e.g. if the service crashes after processing but before committing the Kafka offset).

**Without idempotency**: second delivery → second authorization attempt → consumer charged twice.

**Solution**: dual-layer idempotency guard.

1. **Application layer**: `findByOrderId(orderId)` check before any processing. If a record exists, replay the existing outcome without touching account data.
2. **Database layer**: `UNIQUE` constraint on `payment_authorizations.order_id` as a safety net — even if the application check races, the DB will reject the duplicate insert.

This ensures exactly-once _business semantics_ despite at-least-once _delivery_.

---

## Consequences

### Benefits
- **PCI scope reduction**: Only this service is audited for payment data handling.
- **Independent deployability**: Accounting Service can be scaled, updated, or patched without touching Order or Kitchen services.
- **Clear accountability**: one team owns all payment logic — no cross-team confusion about who handles a bug.
- **Horizontal scalability**: Kafka consumer group allows multiple replicas to share load across partitions.

### Trade-offs

#### Eventual Consistency
The authorization result is delivered asynchronously. The Order Service does not receive the authorization outcome synchronously — it must wait for `payment.authorized` or `payment.failed` on Kafka. This means:
- Order state is **eventually consistent** — there is a brief window where an order is "pending payment".
- The Saga may take longer to complete than a synchronous call would.

This is an **accepted trade-off**: eventual consistency is the correct model for distributed saga steps where failure isolation is more important than latency.

#### What happens if Accounting Service is down when `OrderCreated` fires?

Kafka is the durability layer. The `order.created` topic is a durable log — messages are retained (configurable, default 7 days). When the Accounting Service recovers:
- It reads from its committed offset and processes all missed events.
- Idempotency guards ensure no duplicates are processed if the service was mid-processing when it crashed.

**DLQ strategy**: After `ftgo.kafka.max-retries` (default: 3) failed delivery attempts, the message is forwarded to the `order.created.DLT` (Dead Letter Topic) for manual inspection and replay. An alert/PagerDuty integration on DLT message count is recommended for production.

#### Operational complexity
Running a separate service means a separate:
- Postgres database instance to provision and back up.
- Kafka consumer group to monitor.
- CI/CD pipeline to maintain.
- On-call runbook entry.

This overhead is justified by the PCI compliance and domain separation benefits.

---

## Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Payment logic inside Order Service | Bloats Order Service scope; all of Order Service enters PCI audit scope |
| Synchronous HTTP call from Order Service to a Payment API | Creates tight coupling; single point of failure; no message durability |
| Shared database between Order and Accounting | Violates database-per-service; any Order Service DB migration could corrupt payment records |
| Using a third-party payment SaaS directly from Order Service | Still exposes Order Service to PCI scope; Accounting Service as a gateway keeps PCI boundary clean |
