package com.ftgo.order.service;

import com.ftgo.order.entity.Order;
import com.ftgo.order.entity.OrderStatus;
import com.ftgo.order.events.OrderApprovedEvent;
import com.ftgo.order.events.OrderCancelledEvent;
import com.ftgo.order.publisher.OrderApprovedEventPublisher;
import com.ftgo.order.publisher.OrderCancelledEventPublisher;
import com.ftgo.order.repository.OrderRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class OrderSagaService {

    private final OrderRepository orderRepository;
    private final OrderApprovedEventPublisher approvedPublisher;
    private final OrderCancelledEventPublisher cancelledPublisher;

    public void tryApprove(Long orderId) {

        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new RuntimeException("Order not found"));

        if (order.isKitchenApproved()
                && order.isPaymentApproved()
                && order.getStatus() != OrderStatus.APPROVED) {

            order.setStatus(OrderStatus.APPROVED);

            orderRepository.save(order);

            approvedPublisher.publishOrderApproved(
                    new OrderApprovedEvent(
                            order.getId(),
                            order.getConsumerId(),
                            order.getRestaurantId(),
                            order.getTotalAmount(),
                            order.getStatus()));
        }
    }

    public void cancelOrder(Long orderId) {

        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new RuntimeException("Order not found"));

        if (order.getStatus() != OrderStatus.CANCELLED) {

            order.setStatus(OrderStatus.CANCELLED);

            orderRepository.save(order);

            cancelledPublisher.publishOrderCancelled(
                    new OrderCancelledEvent(
                            order.getId(),
                            order.getConsumerId(),
                            order.getRestaurantId(),
                            order.getTotalAmount(),
                            order.getStatus()));
        }
    }
}