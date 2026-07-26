# Integration 1 & 2 Troubleshooting & Resolution Log

> **Project:** FTGO Microservices Platform  
> **Workflows:** `/integration-1-docker-compose` & `/integration-2-e2e-test`  
> **Date:** July 26, 2026  
> **Status:** All 18 Containers Healthy | End-to-End Order Flow Verified (7/7 PASS)

---

## Executive Summary

During the execution of **Integration 1** (Docker Compose Full Stack) and **Integration 2** (End-to-End Order Flow Test), several build, configuration, bean initialization, port mapping, and routing issues were encountered across the microservices and edge gateway stack.

This document records each issue faced, the root cause analysis, how it was diagnosed, and the exact changes made to resolve it.

---

## Summary Table of Issues & Fixes

| # | Issue | Impacted Component | Root Cause | Resolution |
|---|---|---|---|---|
| **1** | Docker build path not found | `docker-compose.yml` | Path specified as `./ftgo-restaurant-service` instead of root folder name `./restaurant-service` | Updated build context in `docker-compose.yml` to point to correct directory names |
| **2** | Missing `ftgo-api-gateway` directory | `docker-compose.yml` | `docker-compose.yml` referenced `./ftgo-api-gateway`, which did not exist on `dev` branch | Created lightweight `ftgo-api-gateway/` container mapping requests to microservice controllers |
| **3** | Dockerfile build failure (`lstat /target`) | `accounting-service`, `order-history-service` | Dockerfiles copied pre-built `target/*.jar`, failing when built from clean source | Converted Dockerfiles to 2-stage Maven builds (`maven:3.9-eclipse-temurin-17`) |
| **4** | Kafka healthcheck failure | `kafka` container | Healthcheck used `localhost:9092` which did not match container internal listener | Updated healthcheck command to `kafka-topics --bootstrap-server kafka:29092 --list` |
| **5** | Accounting Service startup crash | `ftgo-accounting-service` | `FtgoAccountingServiceApplication` class was declared `final`, breaking Spring CGLIB proxying | Removed `final` modifier and private constructor from entrypoint class |
| **6** | Circular bean dependency | `ftgo-consumer-service` | `KafkaConsumerConfig` injected `ConcurrentKafkaListenerContainerFactory` into its own factory bean method | Updated method parameter to inject `ConsumerFactory<String, Object>` |
| **7** | Container port mismatch | All 6 domain microservices | Microservice `application.properties` hardcoded `server.port` to `8081-8086`, conflicting with `docker-compose.yml` `808x:8080` mappings | Added `SERVER_PORT: 8080` environment variable to all microservice definitions in `docker-compose.yml` |
| **8** | Missing `/health` endpoints | `consumer-service`, `order-history-service` | Microservices returned 404 on health probes | Added `HealthController.java` returning HTTP 200 `{"status": "UP"}` |
| **9** | Order History 404 Route Not Found | `Universal-AI-Gateway` | `proxy_config.py` lacked `/api/order-history` in `FTGO_ROUTES` | Added `RouteConfig` for `/api/order-history` and rebuilt container image |
| **10** | Database schema missing | `postgres-gateway` | Gateway database tables were uninitialized on fresh container startup | Ran `alembic upgrade head` to initialize `tenants`, `api_keys`, and `request_logs` tables |

---

## Detailed Technical Explanations

### Issue 1 & 2: Build Path & Gateway Directory Resolution
* **Symptom:** `docker compose build` failed with `unable to prepare context: path "D:\ftgo-project\ftgo-restaurant-service" not found`.
* **Root Cause:** Directory names in repo root were `restaurant-service/` and `kitchen-service/`, whereas `docker-compose.yml` searched for `ftgo-restaurant-service/`. Additionally, the internal API gateway folder `./ftgo-api-gateway` was missing from `dev`.
* **Fix:** Corrected build context paths in `docker-compose.yml` and implemented `ftgo-api-gateway/main.py` & `Dockerfile` to handle Layer 2 internal proxying.

### Issue 3: Multi-Stage Dockerfile Conversion
* **Symptom:** `target ftgo-accounting-service: failed to solve: lstat /target: no such file or directory`.
* **Root Cause:** The Dockerfile assumed a pre-built JAR was compiled on the host before `docker build`.
* **Fix:** Converted `ftgo-accounting-service/Dockerfile` and `ftgo-order-history-service/Dockerfile` to multi-stage builds (`stage 1: maven builder`, `stage 2: eclipse-temurin runtime`).

### Issue 5: Spring CGLIB Proxying Constraint
* **Symptom:** `BeanDefinitionParsingException: Configuration problem: @Configuration class 'FtgoAccountingServiceApplication' may not be final`.
* **Root Cause:** Spring Framework relies on CGLIB sub-classing to generate proxy beans for `@Configuration` classes, which Java forbids on `final` classes.
* **Fix:** Removed `final` keyword in `FtgoAccountingServiceApplication.java`.

### Issue 6: Circular Dependency in Kafka Config
* **Symptom:** `Requested bean is currently in creation: Is there an unresolvable circular reference`.
* **Root Cause:** `kafkaListenerContainerFactory` bean definition requested an instance of `ConcurrentKafkaListenerContainerFactory` as a parameter to its own creation method.
* **Fix:** Changed parameter to `ConsumerFactory<String, Object>` in `KafkaConsumerConfig.java`.

### Issue 7: Port Alignment Across Docker Network
* **Symptom:** Microservice containers started up, but health requests failed with `Remote end closed connection without response`.
* **Root Cause:** Individual `application.properties` hardcoded `server.port=8082` (or `8081`), while `docker-compose.yml` forwarded host ports to container port `8080`.
* **Fix:** Injected `SERVER_PORT: 8080` in `docker-compose.yml` environment blocks, forcing Tomcat inside every container to listen on port `8080`.

---

## Verification Results

After applying all fixes, the entire stack was verified:
1. **`docker compose ps`**: All 18 containers active and healthy.
2. **Health Checks**: 8/8 services returned HTTP 200 OK.
3. **E2E Order Flow Test (`scratch/test_e2e_flow.py`)**: 7/7 test steps passed (`Consumer created`, `Restaurant created`, `Order placed`, `Saga completed`, `API composition`, `CQRS history`, `Gateway audit DB`).
