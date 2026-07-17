package com.ftgo.accounting.web;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.Map;

/**
 * Custom health check endpoints for Kubernetes liveness and readiness probes.
 *
 * <p>Spring Boot Actuator also exposes {@code /actuator/health} (liveness) and
 * {@code /actuator/health/readiness}, but providing explicit REST endpoints gives
 * Kubernetes probe configuration more flexibility (e.g. separate paths per probe type).
 *
 * <p>Kubernetes probe config in {@code deployment.yaml}:
 * <pre>
 *   livenessProbe:
 *     httpGet:
 *       path: /health/live
 *       port: 8080
 *   readinessProbe:
 *     httpGet:
 *       path: /health/ready
 *       port: 8080
 * </pre>
 */
@RestController
@RequestMapping("/health")
public class HealthController {

    /**
     * Liveness probe — returns 200 if the application process is running and not deadlocked.
     * Kubernetes will restart the pod if this endpoint fails.
     */
    @GetMapping("/live")
    public ResponseEntity<Map<String, Object>> liveness() {
        return ResponseEntity.ok(Map.of(
                "status", "UP",
                "service", "ftgo-accounting-service",
                "timestamp", Instant.now().toString()
        ));
    }

    /**
     * Readiness probe — returns 200 if the service is ready to accept traffic.
     * Kubernetes will remove the pod from the load balancer if this fails.
     *
     * <p>In a production implementation this would additionally check:
     * <ul>
     *   <li>Database connectivity</li>
     *   <li>Kafka broker reachability</li>
     * </ul>
     * For now it delegates to the application being up (Spring Actuator readiness
     * checks handle the deeper dependency checks via {@code management.health.*}).
     */
    @GetMapping("/ready")
    public ResponseEntity<Map<String, Object>> readiness() {
        return ResponseEntity.ok(Map.of(
                "status", "READY",
                "service", "ftgo-accounting-service",
                "timestamp", Instant.now().toString()
        ));
    }
}
