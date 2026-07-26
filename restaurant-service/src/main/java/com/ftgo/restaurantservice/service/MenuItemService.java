package com.ftgo.restaurantservice.service;

import com.ftgo.restaurantservice.dto.MenuItemCreateRequest;
import com.ftgo.restaurantservice.dto.MenuItemResponse;
import com.ftgo.restaurantservice.dto.MenuItemUpdateRequest;
import com.ftgo.restaurantservice.entity.MenuItem;
import com.ftgo.restaurantservice.entity.Restaurant;
import com.ftgo.restaurantservice.exception.ResourceNotFoundException;
import com.ftgo.restaurantservice.kafka.MenuChangeType;
import com.ftgo.restaurantservice.kafka.MenuEventProducer;
import com.ftgo.restaurantservice.mapper.MenuItemMapper;
import com.ftgo.restaurantservice.repository.MenuItemRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class MenuItemService {

    private final MenuItemRepository menuItemRepository;
    private final RestaurantService restaurantService;
    private final MenuItemMapper menuItemMapper;
    private final MenuEventProducer menuEventProducer;

    @Transactional
    public MenuItemResponse create(UUID restaurantId, MenuItemCreateRequest request) {
        Restaurant restaurant = restaurantService.getRestaurantOrThrow(restaurantId);
        MenuItem menuItem = menuItemMapper.toEntity(request, restaurant);
        MenuItem savedMenuItem = menuItemRepository.save(menuItem);
        publishAfterCommit(savedMenuItem, MenuChangeType.CREATED);
        return menuItemMapper.toResponse(savedMenuItem);
    }

    @Transactional(readOnly = true)
    public List<MenuItemResponse> findAllByRestaurant(UUID restaurantId) {
        restaurantService.getRestaurantOrThrow(restaurantId);
        return menuItemRepository.findByRestaurantIdOrderByNameAsc(restaurantId)
                .stream()
                .map(menuItemMapper::toResponse)
                .toList();
    }

    @Transactional(readOnly = true)
    public MenuItemResponse findById(UUID restaurantId, UUID menuItemId) {
        return menuItemMapper.toResponse(getMenuItemOrThrow(restaurantId, menuItemId));
    }

    @Transactional
    public MenuItemResponse update(UUID restaurantId, UUID menuItemId, MenuItemUpdateRequest request) {
        MenuItem menuItem = getMenuItemOrThrow(restaurantId, menuItemId);
        menuItemMapper.updateEntity(menuItem, request);
        MenuItem savedMenuItem = menuItemRepository.saveAndFlush(menuItem);
        publishAfterCommit(savedMenuItem, MenuChangeType.UPDATED);
        return menuItemMapper.toResponse(savedMenuItem);
    }

    @Transactional
    public void delete(UUID restaurantId, UUID menuItemId) {
        MenuItem menuItem = getMenuItemOrThrow(restaurantId, menuItemId);
        menuItem.setAvailable(false);
        MenuItem savedMenuItem = menuItemRepository.saveAndFlush(menuItem);
        menuItemRepository.delete(savedMenuItem);
        publishAfterCommit(savedMenuItem, MenuChangeType.DELETED);
    }

    private MenuItem getMenuItemOrThrow(UUID restaurantId, UUID menuItemId) {
        return menuItemRepository.findByIdAndRestaurantId(menuItemId, restaurantId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Menu item not found: " + menuItemId + " for restaurant: " + restaurantId
                ));
    }

    private void publishAfterCommit(MenuItem menuItem, MenuChangeType changeType) {
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                menuEventProducer.publishMenuUpdated(menuItem, changeType);
            }
        });
    }
}
