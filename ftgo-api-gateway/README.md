# API Gateway

> **Owner:** Pranav Nair
> **Part of:** FTGO Microservices Deployment — DevOps Course Project

---

## What This Service Does

The FTGO API Gateway acts as the internal routing layer for the FTGO system.
It is built with Python and FastAPI, serving as a single entry point for routing requests to various microservices based on paths.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/actuator/health` | Service health check |
| GET | `/health` | Service health check |
| ANY | `/{service_name}` | Routes to upstream service |
| ANY | `/{service_name}/{path:path}` | Routes to upstream service |

Routing configuration:
- `/orders` -> `http://ftgo-order-service:8080/orders`
- `/consumers` -> `http://ftgo-consumer-service:8080/consumers`
- `/kitchen` -> `http://ftgo-kitchen-service:8082/api/kitchen`
- `/restaurants` -> `http://ftgo-restaurant-service:8081/api/restaurants`
- `/accounting` -> `http://ftgo-accounting-service:80/accounting`
- `/order-history` -> `http://ftgo-order-history-service:8080/orders`

---

## Local Development

### Prerequisites

- Python 3
- Required packages from `requirements.txt`

### Run this service in isolation

```bash
cd ftgo-api-gateway

# Install dependencies
pip install -r requirements.txt

# Run
uvicorn main:app --reload --port 8000
```
