package com.ftgo.order.repository;

import com.ftgo.order.entity.Order;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface OrderRepository extends JpaRepository<Order, Long> {
    List<Order> findAllByConsumerId(Long consumerId);
}