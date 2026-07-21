# Person 4 Notes

## Responsibilities

- Develop the Consumer Service
- Develop the Order History Service
- Create Kubernetes manifests
- Configure CI/CD workflows
- Maintain ADR-005 (Consumer & Order History CQRS)

---

# Current Project Status

## Existing Modules

- ftgo-consumer-service
- ftgo-consumer-service-api

## Modules to Build

- Standalone Consumer Service = done 
- Order History Service= soon

---

# Consumer Service Analysis

## ConsumerController

### Base Path

```
/consumers
```

### Endpoints

| Method | Endpoint | Purpose |
|---------|----------|---------|
| POST | `/consumers` | Create a new consumer |
| GET | `/consumers/{consumerId}` | Retrieve consumer details |

### Dependencies

- ConsumerService

### DTOs

- CreateConsumerRequest
- CreateConsumerResponse
- GetConsumerResponse

---

## ConsumerService

### Responsibilities

- Create a new consumer
- Retrieve a consumer by ID
- Validate whether a consumer is allowed to place an order

### Dependencies

- ConsumerRepository
- Consumer Entity

### Core Methods

```java
create(PersonName)
findById(long)
validateOrderForConsumer(long, Money)
```

---

## Consumer Entity

### Database Table

```
consumers
```

### Fields

| Field | Type |
|-------|------|
| id | Long (Auto-generated) |
| name | PersonName |

### Business Methods

```java
validateOrderByConsumer(Money)
```

### Purpose

Represents a consumer stored in the Consumer Service database.

---

## ConsumerRepository

### Extends

```java
CrudRepository<Consumer, Long>
```

### Common Operations

- save()
- findById()
- findAll()
- deleteById()

### Purpose

Provides CRUD operations for Consumer entities.

---

## PersonName

### Type

```
@Embeddable
```

### Fields

- firstName
- lastName

### Purpose

Represents a consumer's name as a value object embedded within the Consumer entity.

---

# Architecture Overview

```
REST API
    │
    ▼
ConsumerController
    │
    ▼
ConsumerService
    │
    ▼
ConsumerRepository
    │
    ▼
PostgreSQL Database
```

---

# Order History Service (Planned)

## Responsibilities

- Maintain a read-only Order History view
- Consume domain events from other services
- Store a denormalized, query-optimized database
- Expose APIs for retrieving order history

### Expected Event Sources

- OrderCreated
- OrderCancelled
- TicketCreated
- TicketRejected
- PaymentAuthorized
- PaymentFailed
- DeliveryCompleted

---
