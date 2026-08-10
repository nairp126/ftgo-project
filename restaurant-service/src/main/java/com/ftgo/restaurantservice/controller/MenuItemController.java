package com.ftgo.restaurantservice.controller;

import com.ftgo.restaurantservice.dto.MenuItemCreateRequest;
import com.ftgo.restaurantservice.dto.MenuItemResponse;
import com.ftgo.restaurantservice.dto.MenuItemUpdateRequest;
import com.ftgo.restaurantservice.service.MenuItemService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/restaurants/{restaurantId}/menu-items")
@RequiredArgsConstructor
public class MenuItemController {

    private final MenuItemService menuItemService;

    @PostMapping
    public ResponseEntity<MenuItemResponse> create(
            @PathVariable UUID restaurantId,
            @Valid @RequestBody MenuItemCreateRequest request
    ) {
        return ResponseEntity.status(HttpStatus.CREATED).body(menuItemService.create(restaurantId, request));
    }

    @GetMapping
    public ResponseEntity<List<MenuItemResponse>> findAllByRestaurant(@PathVariable UUID restaurantId) {
        return ResponseEntity.ok(menuItemService.findAllByRestaurant(restaurantId));
    }

    @GetMapping("/{menuItemId}")
    public ResponseEntity<MenuItemResponse> findById(
            @PathVariable UUID restaurantId,
            @PathVariable UUID menuItemId
    ) {
        return ResponseEntity.ok(menuItemService.findById(restaurantId, menuItemId));
    }

    @PutMapping("/{menuItemId}")
    public ResponseEntity<MenuItemResponse> update(
            @PathVariable UUID restaurantId,
            @PathVariable UUID menuItemId,
            @Valid @RequestBody MenuItemUpdateRequest request
    ) {
        return ResponseEntity.ok(menuItemService.update(restaurantId, menuItemId, request));
    }

    @DeleteMapping("/{menuItemId}")
    public ResponseEntity<Void> delete(
            @PathVariable UUID restaurantId,
            @PathVariable UUID menuItemId
    ) {
        menuItemService.delete(restaurantId, menuItemId);
        return ResponseEntity.noContent().build();
    }
}
