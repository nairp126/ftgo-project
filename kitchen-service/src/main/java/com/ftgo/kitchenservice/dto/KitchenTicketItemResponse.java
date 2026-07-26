package com.ftgo.kitchenservice.dto;

import java.util.UUID;

public record KitchenTicketItemResponse(
        UUID id,
        UUID menuItemId,
        String name,
        int quantity,
        String specialInstructions
) {
}
