package com.ftgo.restaurantservice.service;

import com.ftgo.restaurantservice.dto.RestaurantCreateRequest;
import com.ftgo.restaurantservice.dto.RestaurantResponse;
import com.ftgo.restaurantservice.dto.RestaurantUpdateRequest;
import com.ftgo.restaurantservice.entity.Restaurant;
import com.ftgo.restaurantservice.exception.ResourceNotFoundException;
import com.ftgo.restaurantservice.mapper.RestaurantMapper;
import com.ftgo.restaurantservice.repository.RestaurantRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class RestaurantService {

    private final RestaurantRepository restaurantRepository;
    private final RestaurantMapper restaurantMapper;

    @Transactional
    public RestaurantResponse create(RestaurantCreateRequest request) {
        Restaurant restaurant = restaurantMapper.toEntity(request);
        Restaurant savedRestaurant = restaurantRepository.save(restaurant);
        return restaurantMapper.toResponse(savedRestaurant);
    }

    @Transactional(readOnly = true)
    public List<RestaurantResponse> findAll() {
        return restaurantRepository.findAll()
                .stream()
                .map(restaurantMapper::toResponse)
                .toList();
    }

    @Transactional(readOnly = true)
    public RestaurantResponse findById(UUID restaurantId) {
        return restaurantMapper.toResponse(getRestaurantOrThrow(restaurantId));
    }

    @Transactional
    public RestaurantResponse update(UUID restaurantId, RestaurantUpdateRequest request) {
        Restaurant restaurant = getRestaurantOrThrow(restaurantId);
        restaurantMapper.updateEntity(restaurant, request);
        Restaurant savedRestaurant = restaurantRepository.save(restaurant);
        return restaurantMapper.toResponse(savedRestaurant);
    }

    @Transactional
    public void delete(UUID restaurantId) {
        Restaurant restaurant = getRestaurantOrThrow(restaurantId);
        restaurantRepository.delete(restaurant);
    }

    @Transactional(readOnly = true)
    public Restaurant getRestaurantOrThrow(UUID restaurantId) {
        return restaurantRepository.findById(restaurantId)
                .orElseThrow(() -> new ResourceNotFoundException("Restaurant not found: " + restaurantId));
    }
}
