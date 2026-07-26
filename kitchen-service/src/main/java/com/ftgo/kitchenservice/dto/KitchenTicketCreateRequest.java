package com.ftgo.kitchenservice.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import java.util.List;
import java.util.UUID;

public record KitchenTicketCreateRequest(
        @NotNull(message = "Restaurant id is required")
        UUID restaurantId,

        @NotNull(message = "Order id is required")
        UUID orderId,

        @NotEmpty(message = "Ticket must contain at least one item")
        List<@Valid KitchenTicketItemRequest> items
) {
}
