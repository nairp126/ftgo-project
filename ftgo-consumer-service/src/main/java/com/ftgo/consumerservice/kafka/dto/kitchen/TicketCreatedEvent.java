package com.ftgo.consumerservice.kafka.dto.kitchen;

import java.util.List;

public record TicketCreatedEvent(
        Long orderId,
        Long consumerId,
        List<TicketItemEvent> items
) {
}