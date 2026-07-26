package com.ftgo.kitchenservice.mapper;

import com.ftgo.kitchenservice.dto.KitchenMenuItemResponse;
import com.ftgo.kitchenservice.entity.KitchenMenuItem;
import org.springframework.stereotype.Component;

@Component
public class KitchenMenuItemMapper {

    public KitchenMenuItemResponse toResponse(KitchenMenuItem item) {
        return new KitchenMenuItemResponse(
                item.getId(),
                item.getRestaurantId(),
                item.getName(),
                item.getDescription(),
                item.getPrice(),
                item.isAvailable(),
                item.getCategory(),
                item.getVersion(),
                item.getLastUpdatedAt()
        );
    }
}
