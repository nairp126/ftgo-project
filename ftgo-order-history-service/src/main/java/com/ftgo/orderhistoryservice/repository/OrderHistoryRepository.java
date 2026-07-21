package com.ftgo.orderhistoryservice.repository;

import com.ftgo.orderhistoryservice.entity.OrderHistory;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface OrderHistoryRepository extends JpaRepository<OrderHistory, Long> {

    List<OrderHistory> findByConsumerId(Long consumerId);

}