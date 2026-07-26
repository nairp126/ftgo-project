package com.ftgo.kitchenservice.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record KitchenMenuItemResponse(
        UUID id,
        UUID restaurantId,
        String name,
        String description,
        BigDecimal price,
        boolean available,
        String category,
        long version,
        Instant lastUpdatedAt
) {
}
