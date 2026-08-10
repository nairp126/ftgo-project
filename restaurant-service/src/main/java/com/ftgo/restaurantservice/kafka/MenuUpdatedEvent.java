package com.ftgo.restaurantservice.kafka;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record MenuUpdatedEvent(
        UUID eventId,
        String eventType,
        Instant occurredAt,
        MenuChangeType changeType,
        UUID restaurantId,
        UUID menuItemId,
        String name,
        String description,
        BigDecimal price,
        boolean available,
        String category,
        long version
) {
}
