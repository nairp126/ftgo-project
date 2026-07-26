package com.ftgo.restaurantservice.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record RestaurantCreateRequest(
        @NotBlank(message = "Restaurant name is required")
        @Size(max = 160, message = "Restaurant name must not exceed 160 characters")
        String name,

        @Size(max = 2000, message = "Description must not exceed 2000 characters")
        String description,

        @NotBlank(message = "Restaurant address is required")
        String address,

        @Size(max = 32, message = "Phone number must not exceed 32 characters")
        String phoneNumber
) {
}
