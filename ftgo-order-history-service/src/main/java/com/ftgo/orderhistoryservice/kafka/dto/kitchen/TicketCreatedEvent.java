package com.ftgo.orderhistoryservice.kafka.dto.kitchen;

import java.time.Instant;
import java.util.List;

public record TicketCreatedEvent(
        Long eventId,
        String eventType,
        Instant occurredAt,
        Long ticketId,
        Long orderId,
        Long restaurantId,
        List<TicketItemEvent> items
) {
}