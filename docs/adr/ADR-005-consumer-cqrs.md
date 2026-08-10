# ADR-005: Consumer & Order History CQRS

## Status

Accepted

## Context

The FTGO application requires fast and efficient querying of a customer's order history. Querying the Order Service directly for every request would tightly couple read operations to the write model and reduce scalability.

## Decision

The Order History Service is implemented as a separate CQRS read model.

The service consumes domain events from the Order Service, Kitchen Service, Accounting Service, and Delivery Service to maintain a denormalized, read-optimized database.

The Consumer Service remains responsible for customer profile management, while the Order History Service is responsible only for read operations.

## Consequences

### Advantages

- Fast read performance
- Independent scaling
- Loose coupling
- Optimized read model
- Clear separation between commands and queries

### Trade-offs

- Eventual consistency
- Additional infrastructure
- Event processing complexity
- Duplicate data storage

## Event Sources

- OrderCreated
- OrderCancelled
- TicketCreated
- TicketRejected
- PaymentAuthorized
- PaymentFailed
- DeliveryCompleted

## Alternatives Considered

Using the Order Service directly for all queries was rejected because it would tightly couple read and write workloads and reduce scalability.

## Conclusion

CQRS provides a scalable and maintainable architecture by separating write operations from read operations while allowing the Order History Service to maintain its own optimized view of system data.