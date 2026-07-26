package com.ftgo.restaurantservice.controller;

import com.ftgo.restaurantservice.dto.RestaurantCreateRequest;
import com.ftgo.restaurantservice.dto.RestaurantResponse;
import com.ftgo.restaurantservice.dto.RestaurantUpdateRequest;
import com.ftgo.restaurantservice.service.RestaurantService;
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
@RequestMapping("/api/restaurants")
@RequiredArgsConstructor
public class RestaurantController {

    private final RestaurantService restaurantService;

    @PostMapping
    public ResponseEntity<RestaurantResponse> create(@Valid @RequestBody RestaurantCreateRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(restaurantService.create(request));
    }

    @GetMapping
    public ResponseEntity<List<RestaurantResponse>> findAll() {
        return ResponseEntity.ok(restaurantService.findAll());
    }

    @GetMapping("/{restaurantId}")
    public ResponseEntity<RestaurantResponse> findById(@PathVariable UUID restaurantId) {
        return ResponseEntity.ok(restaurantService.findById(restaurantId));
    }

    @PutMapping("/{restaurantId}")
    public ResponseEntity<RestaurantResponse> update(
            @PathVariable UUID restaurantId,
            @Valid @RequestBody RestaurantUpdateRequest request
    ) {
        return ResponseEntity.ok(restaurantService.update(restaurantId, request));
    }

    @DeleteMapping("/{restaurantId}")
    public ResponseEntity<Void> delete(@PathVariable UUID restaurantId) {
        restaurantService.delete(restaurantId);
        return ResponseEntity.noContent().build();
    }
}
