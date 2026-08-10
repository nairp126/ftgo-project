package com.ftgo.restaurantservice.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record MenuItemResponse(
        UUID id,
        UUID restaurantId,
        String name,
        String description,
        BigDecimal price,
        boolean available,
        String category,
        long version,
        Instant createdAt,
        Instant updatedAt
) {
}
