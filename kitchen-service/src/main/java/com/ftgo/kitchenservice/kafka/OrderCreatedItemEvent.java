package com.ftgo.kitchenservice.kafka;

import java.util.UUID;

public record OrderCreatedItemEvent(
        UUID menuItemId,
        int quantity,
        String specialInstructions
) {
}
