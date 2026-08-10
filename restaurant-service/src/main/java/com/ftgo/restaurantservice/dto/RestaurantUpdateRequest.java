package com.ftgo.restaurantservice.dto;

import com.ftgo.restaurantservice.entity.RestaurantStatus;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record RestaurantUpdateRequest(
        @NotBlank(message = "Restaurant name is required")
        @Size(max = 160, message = "Restaurant name must not exceed 160 characters")
        String name,

        @Size(max = 2000, message = "Description must not exceed 2000 characters")
        String description,

        @NotBlank(message = "Restaurant address is required")
        String address,

        @Size(max = 32, message = "Phone number must not exceed 32 characters")
        String phoneNumber,

        @NotNull(message = "Restaurant status is required")
        RestaurantStatus status
) {
}
