package com.ftgo.kitchenservice.service;

import com.ftgo.kitchenservice.dto.KitchenMenuItemResponse;
import com.ftgo.kitchenservice.entity.KitchenMenuItem;
import com.ftgo.kitchenservice.kafka.MenuChangeType;
import com.ftgo.kitchenservice.kafka.MenuUpdatedEvent;
import com.ftgo.kitchenservice.mapper.KitchenMenuItemMapper;
import com.ftgo.kitchenservice.repository.KitchenMenuItemRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class KitchenMenuService {

    private final KitchenMenuItemRepository kitchenMenuItemRepository;
    private final KitchenMenuItemMapper kitchenMenuItemMapper;

    @Transactional
    public void applyMenuUpdated(MenuUpdatedEvent event) {
        KitchenMenuItem menuItem = kitchenMenuItemRepository.findById(event.menuItemId())
                .orElseGet(() -> KitchenMenuItem.builder().id(event.menuItemId()).build());

        if (menuItem.getVersion() > event.version()) {
            return;
        }

        menuItem.setRestaurantId(event.restaurantId());
        menuItem.setName(event.name());
        menuItem.setDescription(event.description());
        menuItem.setPrice(event.price());
        menuItem.setAvailable(event.changeType() != MenuChangeType.DELETED && event.available());
        menuItem.setCategory(event.category());
        menuItem.setVersion(event.version());
        menuItem.setLastUpdatedAt(event.occurredAt());

        kitchenMenuItemRepository.save(menuItem);
    }

    @Transactional(readOnly = true)
    public List<KitchenMenuItemResponse> findByRestaurant(UUID restaurantId) {
        return kitchenMenuItemRepository.findByRestaurantIdOrderByNameAsc(restaurantId)
                .stream()
                .map(kitchenMenuItemMapper::toResponse)
                .toList();
    }
}
