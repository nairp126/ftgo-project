package com.ftgo.orderhistoryservice.kafka.dto.kitchen;

public record TicketItemEvent(
        Long menuItemId,
        String name,
        int quantity,
        String specialInstructions
) {
}