package com.ftgo.kitchenservice.dto;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.UUID;

public record KitchenTicketItemRequest(
        @NotNull(message = "Menu item id is required")
        UUID menuItemId,

        @Min(value = 1, message = "Quantity must be at least 1")
        int quantity,

        @Size(max = 1000, message = "Special instructions must not exceed 1000 characters")
        String specialInstructions
) {
}
