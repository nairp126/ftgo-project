package com.ftgo.restaurantservice.repository;

import com.ftgo.restaurantservice.entity.MenuItem;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface MenuItemRepository extends JpaRepository<MenuItem, UUID> {

    List<MenuItem> findByRestaurantIdOrderByNameAsc(UUID restaurantId);

    Optional<MenuItem> findByIdAndRestaurantId(UUID id, UUID restaurantId);

    boolean existsByIdAndRestaurantId(UUID id, UUID restaurantId);
}
