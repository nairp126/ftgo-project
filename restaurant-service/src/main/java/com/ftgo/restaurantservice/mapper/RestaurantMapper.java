package com.ftgo.restaurantservice.mapper;

import com.ftgo.restaurantservice.dto.RestaurantCreateRequest;
import com.ftgo.restaurantservice.dto.RestaurantResponse;
import com.ftgo.restaurantservice.dto.RestaurantUpdateRequest;
import com.ftgo.restaurantservice.entity.Restaurant;
import com.ftgo.restaurantservice.entity.RestaurantStatus;
import org.springframework.stereotype.Component;

@Component
public class RestaurantMapper {

    public Restaurant toEntity(RestaurantCreateRequest request) {
        return Restaurant.builder()
                .name(request.name())
                .description(request.description())
                .address(request.address())
                .phoneNumber(request.phoneNumber())
                .status(RestaurantStatus.ACTIVE)
                .build();
    }

    public void updateEntity(Restaurant restaurant, RestaurantUpdateRequest request) {
        restaurant.setName(request.name());
        restaurant.setDescription(request.description());
        restaurant.setAddress(request.address());
        restaurant.setPhoneNumber(request.phoneNumber());
        restaurant.setStatus(request.status());
    }

    public RestaurantResponse toResponse(Restaurant restaurant) {
        return new RestaurantResponse(
                restaurant.getId(),
                restaurant.getName(),
                restaurant.getDescription(),
                restaurant.getAddress(),
                restaurant.getPhoneNumber(),
                restaurant.getStatus(),
                restaurant.getCreatedAt(),
                restaurant.getUpdatedAt()
        );
    }
}
