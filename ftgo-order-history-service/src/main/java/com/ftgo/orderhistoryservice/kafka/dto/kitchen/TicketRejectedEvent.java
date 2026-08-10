package com.ftgo.orderhistoryservice.kafka.dto.kitchen;

import java.time.Instant;

public record TicketRejectedEvent(
        Long eventId,
        String eventType,
        Instant occurredAt,
        Long orderId,
        Long restaurantId,
        String reason
) {
}