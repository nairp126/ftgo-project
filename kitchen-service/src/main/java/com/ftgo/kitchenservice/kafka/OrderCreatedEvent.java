package com.ftgo.kitchenservice.kafka;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record OrderCreatedEvent(
        UUID eventId,
        String eventType,
        Instant occurredAt,
        UUID orderId,
        UUID restaurantId,
        List<OrderCreatedItemEvent> items
) {
}
