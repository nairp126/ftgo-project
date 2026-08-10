package com.ftgo.kitchenservice.repository;

import com.ftgo.kitchenservice.entity.KitchenTicket;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface KitchenTicketRepository extends JpaRepository<KitchenTicket, UUID> {

    List<KitchenTicket> findByRestaurantIdOrderByCreatedAtDesc(UUID restaurantId);

    Optional<KitchenTicket> findByOrderId(UUID orderId);

    boolean existsByOrderId(UUID orderId);
}
