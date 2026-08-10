package com.ftgo.kitchenservice.kafka;

import java.util.UUID;

public record TicketItemEvent(
        UUID menuItemId,
        String name,
        int quantity,
        String specialInstructions
) {
}
