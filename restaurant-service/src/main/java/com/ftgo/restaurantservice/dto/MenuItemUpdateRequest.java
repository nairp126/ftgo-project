package com.ftgo.restaurantservice.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;

public record MenuItemUpdateRequest(
        @NotBlank(message = "Menu item name is required")
        @Size(max = 160, message = "Menu item name must not exceed 160 characters")
        String name,

        @Size(max = 2000, message = "Description must not exceed 2000 characters")
        String description,

        @NotNull(message = "Price is required")
        @DecimalMin(value = "0.01", message = "Price must be greater than zero")
        @Digits(integer = 8, fraction = 2, message = "Price must fit 8 integer digits and 2 decimal places")
        BigDecimal price,

        @NotNull(message = "Availability is required")
        Boolean available,

        @Size(max = 80, message = "Category must not exceed 80 characters")
        String category
) {
}
