package com.ftgo.consumerservice.kafka.dto.kitchen;

public record TicketRejectedEvent(
        Long orderId,
        Long consumerId,
        String reason
) {
}