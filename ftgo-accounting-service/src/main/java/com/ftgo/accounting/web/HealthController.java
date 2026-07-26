package com.ftgo.accounting.web;

import java.time.Instant;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Custom health check endpoints for Kubernetes liveness and readiness probes.
 *
 * <p>Spring Boot Actuator exposes /actuator/health (liveness) and
 * /actuator/health/readiness, but providing explicit REST endpoints gives
 * Kubernetes probe configuration more flexibility.
 *
 * <p>Kubernetes probe config in deployment.yaml:
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
     * Liveness probe returns 200 if the application process is running.
     * Kubernetes will restart the pod if this endpoint fails.
     *
     * @return map containing status UP and timestamp
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
     * Readiness probe returns 200 if the service is ready to accept traffic.
     * Kubernetes will remove the pod from the load balancer if this fails.
     *
     * <p>In a production implementation this would additionally check:
     * <ul>
     *   <li>Database connectivity</li>
     *   <li>Kafka broker reachability</li>
     * </ul>
     * For now it delegates to the application being up.
     *
     * @return map containing status READY and timestamp
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
