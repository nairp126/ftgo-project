# ADR-002: Order Service Boundary and Saga Orchestration

- **Status:** Accepted
- **Date:** 2026-07-25
- **Authors:** Kinjal Srivastava

## Context

The original FTGO application followed a monolithic architecture where order creation, payment processing, kitchen management, and delivery workflow were tightly coupled within a single application.

As the system grows, this architecture introduces several challenges:

- High coupling between business domains
- Difficult independent deployment
- Limited scalability
- Reduced fault isolation
- Complex maintenance and testing

To improve scalability and maintainability, the Order domain has been extracted into an independent microservice.

---

## Decision

The Order Service will own the complete lifecycle of customer orders.

Its responsibilities include:

- Creating new orders
- Persisting order information
- Managing order state transitions
- Publishing domain events
- Consuming events from dependent services
- Coordinating the order workflow using Saga orchestration

The service communicates asynchronously with other microservices through Apache Kafka.

---

## Service Responsibilities

The Order Service is responsible for:

- Order creation
- Order retrieval
- Order status management
- Saga orchestration
- Event publication
- Event consumption
- Persisting order data in its own PostgreSQL database

The service does **not** manage:

- Payment processing
- Kitchen operations
- Delivery assignment
- Customer authentication

These concerns belong to their respective microservices.

---

## Saga Workflow

The Order Service follows the Saga pattern for distributed transaction management.

### Step 1

Customer creates an order.

Order Service:

- Saves the order with status `CREATED`
- Publishes an `OrderCreatedEvent`

---

### Step 2

Payment Service processes payment.

Possible outcomes:

- PaymentApprovedEvent
- PaymentFailedEvent

---

### Step 3

Kitchen Service validates order availability.

Possible outcomes:

- TicketCreatedEvent
- KitchenRejectedEvent

---

### Step 4

Order Service waits until both:

- Payment approved
- Kitchen accepted

When both conditions are satisfied:

- Order status changes to `APPROVED`
- `OrderApprovedEvent` is published

If any service rejects the request:

- Order status changes to `CANCELLED`
- `OrderCancelledEvent` is published

---

## Event-Driven Communication

### Published Events

- OrderCreatedEvent
- OrderApprovedEvent
- OrderCancelledEvent

### Consumed Events

- PaymentApprovedEvent
- PaymentFailedEvent
- TicketCreatedEvent
- KitchenRejectedEvent

Apache Kafka is used as the messaging backbone for asynchronous communication.

---

## Data Ownership

The Order Service owns its database.

No external service directly modifies Order data.

Communication between services occurs only through domain events.

This follows the Database per Service pattern.

---

## Benefits

This design provides:

- Loose coupling
- Independent deployment
- Better scalability
- Fault isolation
- Easier maintenance
- Clear service ownership
- Event-driven integration
- Support for distributed transactions using Saga

---

## Consequences

### Positive

- Services evolve independently.
- Failures are isolated.
- Order logic remains centralized.
- Easier future integration with additional services.

### Negative

- Increased architectural complexity.
- Eventual consistency instead of ACID transactions.
- Additional monitoring and observability requirements.
- More complex debugging across services.

---

## Alternatives Considered

### Monolithic Transaction

Rejected because it tightly couples multiple business domains and prevents independent scaling.

### Distributed Two-Phase Commit (2PC)

Rejected due to poor scalability, tight coupling, and reduced fault tolerance across microservices.

### Choreography-Based Saga

Considered, but orchestration was chosen because the Order Service naturally acts as the central coordinator for the order lifecycle, making the workflow easier to understand and maintain.

---

## Decision Summary

The Order Service is implemented as an independent microservice responsible for managing customer orders and coordinating the order lifecycle using the Saga orchestration pattern with Apache Kafka for asynchronous communication.

This approach improves modularity, scalability, maintainability, and aligns with the overall microservices migration strategy for FTGO.
