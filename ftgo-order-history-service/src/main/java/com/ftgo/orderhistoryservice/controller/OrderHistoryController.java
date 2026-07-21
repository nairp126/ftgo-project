package com.ftgo.orderhistoryservice.controller;

import com.ftgo.orderhistoryservice.dto.OrderHistoryRequest;
import com.ftgo.orderhistoryservice.dto.OrderHistoryResponse;
import com.ftgo.orderhistoryservice.entity.OrderHistory;
import com.ftgo.orderhistoryservice.service.OrderHistoryService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.stream.Collectors;

@RestController
@RequestMapping("/orders")
public class OrderHistoryController {

    private final OrderHistoryService service;

    public OrderHistoryController(OrderHistoryService service) {
        this.service = service;
    }

    @GetMapping
    public List<OrderHistoryResponse> getAllOrders() {
        return service.getAllOrders()
                .stream()
                .map(this::toResponse)
                .collect(Collectors.toList());
    }

    @GetMapping("/{id}")
    public OrderHistoryResponse getOrder(@PathVariable Long id) {
        return toResponse(service.getOrder(id));
    }

    @GetMapping("/consumer/{consumerId}")
    public List<OrderHistoryResponse> getOrdersByConsumerId(@PathVariable Long consumerId) {
        return service.getOrdersByConsumerId(consumerId)
                .stream()
                .map(this::toResponse)
                .collect(Collectors.toList());
    }

    @PostMapping
    public OrderHistoryResponse createOrder(@Valid @RequestBody OrderHistoryRequest request) {

        OrderHistory order = new OrderHistory(
                request.getConsumerId(),
                request.getOrderId(),
                request.getRestaurantName(),
                request.getTotalAmount(),
                request.getOrderStatus(),
                request.getOrderDate()
        );

        return toResponse(service.saveOrder(order));
    }

    @DeleteMapping("/{id}")
    public void deleteOrder(@PathVariable Long id) {
        service.deleteOrder(id);
    }

    private OrderHistoryResponse toResponse(OrderHistory order) {

        OrderHistoryResponse response = new OrderHistoryResponse();

        response.setId(order.getId());
        response.setConsumerId(order.getConsumerId());
        response.setOrderId(order.getOrderId());
        response.setRestaurantName(order.getRestaurantName());
        response.setTotalAmount(order.getTotalAmount());
        response.setOrderStatus(order.getOrderStatus());
        response.setOrderDate(order.getOrderDate());

        return response;
    }
}