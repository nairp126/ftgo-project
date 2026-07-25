package com.ftgo.order.consumer;

import com.ftgo.order.entity.Order;
import com.ftgo.order.events.TicketCreatedEvent;
import com.ftgo.order.repository.OrderRepository;
import com.ftgo.order.service.OrderSagaService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;

@Service
@Slf4j
@RequiredArgsConstructor
public class TicketCreatedConsumer {

    private final OrderRepository orderRepository;
    private final OrderSagaService orderSagaService;

    @KafkaListener(topics = "ftgo.kitchen.ticket-created", groupId = "order-service-group")
    public void consumeTicketCreated(TicketCreatedEvent event) {

        log.info("Received TicketCreatedEvent: {}", event);

        Order order = orderRepository.findById(event.getOrderId())
                .orElseThrow(() -> new IllegalArgumentException("Order not found: " + event.getOrderId()));

        order.setKitchenApproved(true);

        orderRepository.save(order);

        orderSagaService.tryApprove(order.getId());
    }
}