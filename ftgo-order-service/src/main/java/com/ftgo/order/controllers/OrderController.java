package com.ftgo.order.controllers;

import com.ftgo.order.dto.CreateOrderRequest;
import com.ftgo.order.dto.CreateOrderResponse;
import com.ftgo.order.dto.GetOrderResponse;
import com.ftgo.order.service.OrderService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;

    @Autowired
    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    /**
     * Create a new order.
     *
     * @param createOrderRequest the order creation request
     * @return ResponseEntity with the created order response
     */
    @PostMapping
    public ResponseEntity<CreateOrderResponse> createOrder(
            @RequestBody CreateOrderRequest createOrderRequest) {
        CreateOrderResponse response = orderService.createOrder(createOrderRequest);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    /**
     * Get an order by ID.
     *
     * @param id the order ID
     * @return ResponseEntity with the order details
     */
    @GetMapping("/{id}")
    public ResponseEntity<GetOrderResponse> getOrder(@PathVariable Long id) {
        GetOrderResponse response = orderService.getOrderById(id);
        return ResponseEntity.ok(response);
    }

    /**
     * Get all orders for a specific consumer.
     *
     * @param consumerId the consumer ID
     * @return ResponseEntity with list of consumer orders
     */
    @GetMapping
    public ResponseEntity<List<GetOrderResponse>> getOrdersByConsumer(
            @RequestParam Long consumerId) {
        List<GetOrderResponse> orders = orderService.getOrdersByConsumer(consumerId);
        return ResponseEntity.ok(orders);
    }

    /**
     * Cancel an order.
     *
     * @param id the order ID to cancel
     * @return ResponseEntity with cancellation response
     */
    @PostMapping("/{id}/cancel")
    public ResponseEntity<CreateOrderResponse> cancelOrder(@PathVariable Long id) {
        CreateOrderResponse response = orderService.cancelOrder(id);
        return ResponseEntity.ok(response);
    }
}
