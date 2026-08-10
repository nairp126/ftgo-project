package com.ftgo.kitchenservice.repository;

import com.ftgo.kitchenservice.entity.KitchenMenuItem;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface KitchenMenuItemRepository extends JpaRepository<KitchenMenuItem, UUID> {

    List<KitchenMenuItem> findByRestaurantIdOrderByNameAsc(UUID restaurantId);
}
