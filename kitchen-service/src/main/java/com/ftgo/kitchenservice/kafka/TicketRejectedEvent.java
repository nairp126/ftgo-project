package com.ftgo.kitchenservice.kafka;

import java.time.Instant;
import java.util.UUID;

public record TicketRejectedEvent(
        UUID eventId,
        String eventType,
        Instant occurredAt,
        UUID orderId,
        UUID restaurantId,
        String reason
) {
}
