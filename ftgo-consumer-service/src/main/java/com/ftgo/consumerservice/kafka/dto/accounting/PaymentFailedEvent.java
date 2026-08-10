package com.ftgo.consumerservice.kafka.dto.accounting;

public record PaymentFailedEvent(
        Long orderId,
        Long consumerId,
        Double amount,
        String reason
) {
}