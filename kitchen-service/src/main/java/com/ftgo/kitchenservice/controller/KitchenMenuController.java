package com.ftgo.kitchenservice.controller;

import com.ftgo.kitchenservice.dto.KitchenMenuItemResponse;
import com.ftgo.kitchenservice.service.KitchenMenuService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/kitchen/menu-items")
@RequiredArgsConstructor
public class KitchenMenuController {

    private final KitchenMenuService kitchenMenuService;

    @GetMapping("/restaurant/{restaurantId}")
    public ResponseEntity<List<KitchenMenuItemResponse>> findByRestaurant(@PathVariable UUID restaurantId) {
        return ResponseEntity.ok(kitchenMenuService.findByRestaurant(restaurantId));
    }
}
