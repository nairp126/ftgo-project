package com.ftgo.kitchenservice.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.Map;

@RestController
public class HealthController {

    @GetMapping("/")
    public ResponseEntity<Map<String, Object>> root() {
        return ResponseEntity.ok(Map.of(
                "service", "kitchen-service",
                "status", "UP",
                "timestamp", Instant.now(),
                "ticketsApi", "/api/kitchen/tickets",
                "localMenuApi", "/api/kitchen/menu-items/restaurant/{restaurantId}"
        ));
    }

    @GetMapping("/health")
    public ResponseEntity<Map<String, Object>> health() {
        return ResponseEntity.ok(Map.of(
                "status", "UP",
                "service", "kitchen-service"
        ));
    }
}
