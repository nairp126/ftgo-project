# Kitchen Service

> **Owner:** Vikrant Rana
> **Part of:** FTGO Microservices Deployment — DevOps Course Project

---

## What This Service Does

The Kitchen Service processes and tracks kitchen tickets.
It is responsible for managing the preparation process of orders in the restaurant's kitchen.

---

## Domain Responsibilities

**Owns:**
- KitchenTicket
- KitchenMenuItem
- KitchenTicketItem

**Does NOT own (and never reads directly):**
- Billing details
- Order history

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/kitchen/menu-items/restaurant/{id}` | Finds menu items by restaurant |
| POST | `/api/kitchen/tickets` | Creates a kitchen ticket |
| GET | `/api/kitchen/tickets` | Lists all tickets |
| GET | `/api/kitchen/tickets/{id}` | Gets ticket details |
| GET | `/api/kitchen/tickets/restaurant/{id}` | Lists tickets by restaurant |
| PATCH | `/api/kitchen/tickets/{id}/accept` | Accepts ticket |
| PATCH | `/api/kitchen/tickets/{id}/preparing` | Marks ticket as preparing |
| PATCH | `/api/kitchen/tickets/{id}/ready` | Marks ticket as ready |
| PATCH | `/api/kitchen/tickets/{id}/cancel` | Cancels ticket |
| DELETE | `/api/kitchen/tickets/{id}` | Deletes ticket |

All endpoints are accessed through the API gateway at `/kitchen`.
Do not call this service's port directly in production.

---

## Kafka Events

### Publishes

| Topic | When | Payload |
|-------|------|---------|
| `kitchen.ticket.events` | When a ticket is created/updated | TicketEvent |

### Consumes

| Topic | From | Action taken |
|-------|------|-------------|
| `order.created` | Order Service | Process order creation |
| `restaurant.menu.updated` | Restaurant Service | Update local menu items cache |

---

## Database Schema

**Database:** PostgreSQL
**Local port:** 5433

---

## Local Development

### Run this service in isolation

```bash
cd kitchen-service

# Build
./mvnw clean package -DskipTests

# Run (requires Kafka and its database to be up)
./mvnw spring-boot:run \
  -Dspring-boot.run.profiles=local
```
