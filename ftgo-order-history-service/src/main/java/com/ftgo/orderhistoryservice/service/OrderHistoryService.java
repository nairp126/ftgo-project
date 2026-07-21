package com.ftgo.orderhistoryservice.service;

import com.ftgo.orderhistoryservice.entity.OrderHistory;
import com.ftgo.orderhistoryservice.repository.OrderHistoryRepository;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class OrderHistoryService {

    private final OrderHistoryRepository repository;

    public OrderHistoryService(OrderHistoryRepository repository) {
        this.repository = repository;
    }

    public List<OrderHistory> getAllOrders() {
        return repository.findAll();
    }

    public List<OrderHistory> getOrdersByConsumerId(Long consumerId) {
        return repository.findByConsumerId(consumerId);
    }

    public OrderHistory getOrder(Long id) {
        return repository.findById(id).orElse(null);
    }

    public OrderHistory saveOrder(OrderHistory orderHistory) {
        return repository.save(orderHistory);
    }

    public void deleteOrder(Long id) {
        repository.deleteById(id);
    }
}