package com.ftgo.order.consumer;

import com.ftgo.order.entity.Order;
import com.ftgo.order.entity.OrderStatus;
import com.ftgo.order.events.OrderApprovedEvent;
import com.ftgo.order.repository.OrderRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;

@Service
@Slf4j
@RequiredArgsConstructor
public class OrderApprovedConsumer {

    private final OrderRepository orderRepository;

    @KafkaListener(topics = "ftgo.order.approved", groupId = "order-service-group")
    public void consumeOrderApproved(OrderApprovedEvent event) {

        log.info("Received OrderApprovedEvent: {}", event);

        Order order = orderRepository.findById(event.getOrderId())
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found with id: " + event.getOrderId()));

        order.setStatus(OrderStatus.APPROVED);

        orderRepository.save(order);

        log.info("Order {} approved successfully.", order.getId());
    }
}