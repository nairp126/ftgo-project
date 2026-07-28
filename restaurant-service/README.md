# Restaurant Service

> **Owner:** Vikrant Rana
> **Part of:** FTGO Microservices Deployment — DevOps Course Project

---

## What This Service Does

The Restaurant Service manages restaurant profiles and menus.
It allows restaurants to create and update their information, as well as manage menu items available for order.

---

## Domain Responsibilities

**Owns:**
- Restaurant
- MenuItem

**Does NOT own (and never reads directly):**
- Orders
- Kitchen tickets

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/restaurants` | Creates a new restaurant |
| GET | `/api/restaurants` | Lists all restaurants |
| GET | `/api/restaurants/{id}` | Gets restaurant details |
| PUT | `/api/restaurants/{id}` | Updates restaurant |
| DELETE | `/api/restaurants/{id}` | Deletes restaurant |
| POST | `/api/restaurants/{id}/menu-items` | Creates a menu item |
| GET | `/api/restaurants/{id}/menu-items` | Lists menu items |
| GET | `/api/restaurants/{id}/menu-items/{menuItemId}` | Gets menu item |
| PUT | `/api/restaurants/{id}/menu-items/{menuItemId}` | Updates menu item |
| DELETE | `/api/restaurants/{id}/menu-items/{menuItemId}` | Deletes menu item |

All endpoints are accessed through the API gateway at `/restaurants`.
Do not call this service's port directly in production.

---

## Kafka Events

### Publishes

| Topic | When | Payload |
|-------|------|---------|
| `restaurant.menu.updated` | Menu is updated/created | MenuUpdatedEvent |

### Consumes

| Topic | From | Action taken |
|-------|------|-------------|

---

## Database Schema

**Database:** PostgreSQL
**Local port:** 5432

---

## Local Development

### Run this service in isolation

```bash
cd restaurant-service

# Build
./mvnw clean package -DskipTests

# Run (requires Kafka and its database to be up)
./mvnw spring-boot:run \
  -Dspring-boot.run.profiles=local
```
