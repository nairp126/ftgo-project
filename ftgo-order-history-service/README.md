# Order History Service

> **Owner:** Anshuman Rangarh
> **Part of:** FTGO Microservices Deployment — DevOps Course Project

---

## What This Service Does

The Order History Service provides a CQRS read model for order history queries.
It aggregates data from multiple services to serve comprehensive order histories to users quickly.

---

## Domain Responsibilities

**Owns:**
- OrderHistory

**Does NOT own (and never reads directly):**
- Kitchen state
- Menu items

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/orders` | Lists all orders |
| GET | `/orders/{id}` | Gets order history by ID |
| GET | `/orders/consumer/{id}` | Gets order history for consumer |
| POST | `/orders` | Creates an order history record |
| DELETE | `/orders/{id}` | Deletes an order history record |

All endpoints are accessed through the API gateway at `/order-history`.
Do not call this service's port directly in production.

---

## Kafka Events

### Publishes

| Topic | When | Payload |
|-------|------|---------|

### Consumes

| Topic | From | Action taken |
|-------|------|-------------|
| `payment.authorized` | Accounting | Updates order history on payment auth |
| `payment.failed` | Accounting | Updates order history on payment failure |
| `ticket.created` | Kitchen | Updates order history on ticket creation |
| `ticket.rejected` | Kitchen | Updates order history on ticket rejection |

---

## Database Schema

**Database:** PostgreSQL
**Local port:** 5432

---

## Local Development

### Run this service in isolation

```bash
cd ftgo-order-history-service

# Build
./mvnw clean package -DskipTests

# Run (requires Kafka and its database to be up)
./mvnw spring-boot:run \
  -Dspring-boot.run.profiles=local
```
