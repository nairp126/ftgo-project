package com.ftgo.restaurantservice.mapper;

import com.ftgo.restaurantservice.dto.MenuItemCreateRequest;
import com.ftgo.restaurantservice.dto.MenuItemResponse;
import com.ftgo.restaurantservice.dto.MenuItemUpdateRequest;
import com.ftgo.restaurantservice.entity.MenuItem;
import com.ftgo.restaurantservice.entity.Restaurant;
import org.springframework.stereotype.Component;

@Component
public class MenuItemMapper {

    public MenuItem toEntity(MenuItemCreateRequest request, Restaurant restaurant) {
        return MenuItem.builder()
                .restaurant(restaurant)
                .name(request.name())
                .description(request.description())
                .price(request.price())
                .available(request.available() == null || request.available())
                .category(request.category())
                .build();
    }

    public void updateEntity(MenuItem menuItem, MenuItemUpdateRequest request) {
        menuItem.setName(request.name());
        menuItem.setDescription(request.description());
        menuItem.setPrice(request.price());
        menuItem.setAvailable(request.available());
        menuItem.setCategory(request.category());
    }

    public MenuItemResponse toResponse(MenuItem menuItem) {
        return new MenuItemResponse(
                menuItem.getId(),
                menuItem.getRestaurant().getId(),
                menuItem.getName(),
                menuItem.getDescription(),
                menuItem.getPrice(),
                menuItem.isAvailable(),
                menuItem.getCategory(),
                menuItem.getVersion(),
                menuItem.getCreatedAt(),
                menuItem.getUpdatedAt()
        );
    }
}
