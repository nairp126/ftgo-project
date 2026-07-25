# FTGO Order Service

The **Order Service** is a Spring Boot microservice responsible for managing customer orders within the FTGO microservices architecture. It owns the complete order lifecycle, persists order data, and coordinates distributed business transactions using the **Saga Orchestration** pattern.

---

## Features

- Create and retrieve customer orders
- Manage order lifecycle and state transitions
- Saga orchestration for distributed transactions
- Asynchronous communication using Apache Kafka
- PostgreSQL persistence
- Docker support for containerized deployment
- Spring Boot Actuator health endpoints

---

## Architecture

```
                +----------------------+
                |      API Gateway     |
                +----------+-----------+
                           |
                           |
                   Order Service
                           |
      +--------------------+--------------------+
      |                    |                    |
      |                    |                    |
Payment Service     Kitchen Service     Other Services
      |                    |
      +--------- Kafka Event Bus --------+
```

The Order Service owns all order-related business logic and communicates with other services through Kafka events.

---

## Technology Stack

| Technology      | Purpose                          |
| --------------- | -------------------------------- |
| Java 17         | Programming Language             |
| Spring Boot     | REST API & Application Framework |
| Spring Data JPA | Database Access                  |
| PostgreSQL      | Persistent Storage               |
| Apache Kafka    | Event-driven Communication       |
| Gradle          | Build Tool                       |
| Docker          | Containerization                 |

---

## Order Lifecycle

```
CREATED
   |
   |---- PaymentApprovedEvent ----+
   |                              |
   |---- TicketCreatedEvent ------+
                                  |
                              APPROVED
```

Failure path:

```
CREATED
   |
   +---- PaymentFailedEvent
   |
   +---- KitchenRejectedEvent
          |
      CANCELLED
```

The Order Service waits for both:

- Payment approval
- Kitchen acceptance

before approving an order.

---

## Published Events

The service publishes the following Kafka events:

- OrderCreatedEvent
- OrderApprovedEvent
- OrderCancelledEvent

---

## Consumed Events

The service consumes the following Kafka events:

- PaymentApprovedEvent
- PaymentFailedEvent
- TicketCreatedEvent
- KitchenRejectedEvent

---

## REST APIs

### Create Order

```
POST /orders
```

Creates a new customer order.

---

### Get Order

```
GET /orders/{orderId}
```

Returns details of a specific order.

---

### Health Check

```
GET /actuator/health
```

Returns the health status of the service.

---

## Database

The Order Service owns its own PostgreSQL database.

Sample configuration:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://postgres-order:5432/orders
    username: postgres
    password: postgrespassword
```

---

## Running Locally

### Clone Repository

```bash
git clone <repository-url>
```

### Build

```bash
./gradlew build
```

### Run

```bash
./gradlew bootRun
```

---

## Running with Docker

Build the Docker image:

```bash
docker build -t ftgo-order-service .
```

Run the service:

```bash
docker compose up --build ftgo-order-service
```

---

## Environment Variables

| Variable                                   | Description                 |
| ------------------------------------------ | --------------------------- |
| SPRING_DATASOURCE_URL                      | PostgreSQL connection URL   |
| SPRING_DATASOURCE_USERNAME                 | Database username           |
| SPRING_DATASOURCE_PASSWORD                 | Database password           |
| EVENTUATELOCAL_KAFKA_BOOTSTRAP_SERVERS     | Kafka broker address        |
| EVENTUATELOCAL_ZOOKEEPER_CONNECTION_STRING | ZooKeeper connection string |

---

## Project Structure

```
src
├── controller
├── dto
├── entity
├── events
├── consumer
├── publisher
├── repository
├── service
└── exception
```

---

## Design Decisions

- Database per Service pattern
- Saga Orchestration for distributed transactions
- Event-driven communication using Kafka
- Loose coupling between microservices
- Independent deployment and scalability

Refer to **ADR-002** for detailed architectural decisions.

---

## Future Enhancements

- Order revision and cancellation workflows
- Retry mechanisms for failed event processing
- Dead Letter Queue (DLQ) support
- Distributed tracing with OpenTelemetry
- Metrics and dashboards using Prometheus and Grafana

---

## Author

**Kinjal Srivastava**

B.Tech Computer Science Engineering  
UPES Dehradun

---

## License

This project is developed as part of the FTGO microservices migration initiative.
