package com.ftgo.kitchenservice.kafka;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record TicketCreatedEvent(
        UUID eventId,
        String eventType,
        Instant occurredAt,
        UUID ticketId,
        UUID orderId,
        UUID restaurantId,
        List<TicketItemEvent> items
) {
}
