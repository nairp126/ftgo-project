package com.ftgo.consumerservice.kafka.dto.kitchen;

public record TicketItemEvent(
        String menuItemName,
        int quantity
) {
}