package com.ftgo.restaurantservice.dto;

import com.ftgo.restaurantservice.entity.RestaurantStatus;

import java.time.Instant;
import java.util.UUID;

public record RestaurantResponse(
        UUID id,
        String name,
        String description,
        String address,
        String phoneNumber,
        RestaurantStatus status,
        Instant createdAt,
        Instant updatedAt
) {
}
