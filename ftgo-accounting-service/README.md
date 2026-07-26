# FTGO Accounting Service

This is the Accounting Service for the FTGO microservices project, responsible for managing consumer accounts and payment authorizations as a Saga participant.

## Prerequisites

- **Java 17** (e.g., Eclipse Temurin)
- **Maven** (to build the project or use the wrapper)
- **Docker & Docker Compose** (for running the full stack with Postgres and Kafka)
- **PostgreSQL** (if running locally without Docker)
- **Kafka** (if running locally without Docker)

## 1. Running Unit Tests

The unit tests use an in-memory H2 database and do not require Postgres or Kafka to be running.

```bash
# Navigate to the service directory
cd ftgo-accounting-service

# Run tests
./mvnw test
# or if you don't have the wrapper yet:
mvn test
```

## 2. Running Locally (Development)

To run the application locally, you will need Postgres and Kafka running. You can override the default connection strings using environment variables.

```bash
# Generate the Maven wrapper if you haven't already
mvn wrapper:wrapper

# Run the Spring Boot application
export DB_URL=jdbc:postgresql://localhost:5432/ftgo_accounting
export DB_USERNAME=ftgo_accounting
export DB_PASSWORD=changeme
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092

./mvnw spring-boot:run
```

## 3. Building and Running with Docker

You can build the production-ready layered Docker image and run it locally.

```bash
# Build the Docker image
docker build -t ghcr.io/ftgo/ftgo-accounting-service:latest .

# Run the Docker container
docker run -p 8080:8080 \
  -e DB_URL=jdbc:postgresql://host.docker.internal:5432/ftgo_accounting \
  -e DB_USERNAME=ftgo_accounting \
  -e DB_PASSWORD=changeme \
  -e KAFKA_BOOTSTRAP_SERVERS=host.docker.internal:9092 \
  ghcr.io/ftgo/ftgo-accounting-service:latest
```

## 4. Deploying to Kubernetes

If you have a local Kubernetes cluster (like Minikube or Docker Desktop K8s) and `kubectl` configured:

```bash
# Navigate to the k8s directory
cd ../k8s/accounting-service

# Apply all manifests
kubectl apply -f .
```

*Note: Ensure you have deployed a Postgres database and Kafka broker to your cluster before the Accounting Service can become fully `Ready`.*
