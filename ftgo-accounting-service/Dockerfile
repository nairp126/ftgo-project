# ─── Stage 1: Build ───────────────────────────────────────────────────────────
# Uses the full JDK image to compile and package the application.
FROM eclipse-temurin:17-jdk-alpine AS builder

WORKDIR /workspace

# Copy Maven wrapper and POM first (layer caching: only re-download deps if pom.xml changes)
COPY pom.xml .
COPY .mvn/ .mvn/
COPY mvnw .

# Download dependencies (cached layer)
RUN chmod +x ./mvnw && ./mvnw dependency:go-offline -B

# Copy source and build (skip tests; they run in CI)
COPY src/ src/
RUN ./mvnw package -DskipTests -B

# Extract layered JAR for optimised container image layers
RUN java -Djarmode=layertools -jar target/*.jar extract

# ─── Stage 2: Runtime ─────────────────────────────────────────────────────────
# Uses slim JRE image — no compiler, smaller attack surface (PCI compliance benefit).
FROM eclipse-temurin:17-jre-alpine AS runtime

# Non-root user for security hardening (PCI DSS requirement: least privilege)
RUN addgroup -S ftgo && adduser -S ftgo -G ftgo
USER ftgo

WORKDIR /app

# Copy layered JAR contents in order of changefrequency (cache-friendly)
COPY --from=builder --chown=ftgo:ftgo /workspace/dependencies/ ./
COPY --from=builder --chown=ftgo:ftgo /workspace/spring-boot-loader/ ./
COPY --from=builder --chown=ftgo:ftgo /workspace/snapshot-dependencies/ ./
COPY --from=builder --chown=ftgo:ftgo /workspace/application/ ./

# Expose application port
EXPOSE 8080

# JVM tuning for containers: respect cgroup memory limits, enable GC logging
ENV JAVA_OPTS="-XX:+UseContainerSupport \
               -XX:MaxRAMPercentage=75.0 \
               -XX:+UseG1GC \
               -Djava.security.egd=file:/dev/./urandom"

# Health check (Docker-level, separate from Kubernetes probes)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health/live || exit 1

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS org.springframework.boot.loader.launch.JarLauncher"]
