package com.ftgo.consumerservice.kafka.dto.accounting;

public record PaymentAuthorizedEvent(
        Long orderId,
        Long consumerId,
        Double amount
) {
}