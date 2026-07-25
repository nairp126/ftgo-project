package com.ftgo.order.service;

import com.ftgo.order.dto.CreateOrderRequest;
import com.ftgo.order.dto.CreateOrderResponse;
import com.ftgo.order.dto.GetOrderResponse;
import com.ftgo.order.entity.Order;
import com.ftgo.order.entity.OrderStatus;
import com.ftgo.order.exception.OrderNotFoundException;
import com.ftgo.order.repository.OrderRepository;

import com.ftgo.order.events.OrderCreatedEvent;
import com.ftgo.order.publisher.OrderEventPublisher;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor

public class OrderService {

    private final OrderRepository orderRepository;
    private final OrderEventPublisher orderEventPublisher;

    /**
     * Create a new order.
     *
     * @param createOrderRequest the order creation request
     * @return CreateOrderResponse with the created order details
     */
    public CreateOrderResponse createOrder(CreateOrderRequest createOrderRequest) {
        Order order = Order.builder()
                .consumerId(createOrderRequest.getConsumerId())
                .restaurantId(createOrderRequest.getRestaurantId())
                .totalAmount(createOrderRequest.getTotalAmount())
                .status(OrderStatus.CREATED)
                .createdAt(LocalDateTime.now())
                .build();

        Order savedOrder = orderRepository.save(order);

        OrderCreatedEvent event = OrderCreatedEvent.builder()
                .orderId(savedOrder.getId())
                .consumerId(savedOrder.getConsumerId())
                .restaurantId(savedOrder.getRestaurantId())
                .totalAmount(savedOrder.getTotalAmount())
                .status(savedOrder.getStatus())
                .build();

        orderEventPublisher.publishOrderCreated(event);

        return CreateOrderResponse.builder()
                .orderId(savedOrder.getId())
                .message("Order created successfully")
                .build();
    }

    /**
     * Get an order by ID.
     *
     * @param id the order ID
     * @return GetOrderResponse with order details
     * @throws OrderNotFoundException if order not found
     */
    public GetOrderResponse getOrderById(Long id) {
        Order order = orderRepository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));
        return mapOrderToResponse(order);
    }

    /**
     * Get all orders for a specific consumer.
     *
     * @param consumerId the consumer ID
     * @return List of GetOrderResponse for the consumer
     */
    public List<GetOrderResponse> getOrdersByConsumer(Long consumerId) {
        List<Order> orders = orderRepository.findAllByConsumerId(consumerId);
        return orders.stream()
                .map(this::mapOrderToResponse)
                .collect(Collectors.toList());
    }

    /**
     * Cancel an order.
     *
     * @param id the order ID to cancel
     * @return CreateOrderResponse with cancellation details
     * @throws OrderNotFoundException if order not found
     */
    public CreateOrderResponse cancelOrder(Long id) {
        Order order = orderRepository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        order.setStatus(OrderStatus.CANCELLED);
        orderRepository.save(order);

        return CreateOrderResponse.builder()
                .orderId(order.getId())
                .message("Order cancelled successfully")
                .build();
    }

    /**
     * Map Order entity to GetOrderResponse DTO.
     *
     * @param order the order entity
     * @return GetOrderResponse DTO
     */
    private GetOrderResponse mapOrderToResponse(Order order) {
        return GetOrderResponse.builder()
                .id(order.getId())
                .consumerId(order.getConsumerId())
                .restaurantId(order.getRestaurantId())
                .status(order.getStatus())
                .totalAmount(order.getTotalAmount())
                .build();
    }
}
