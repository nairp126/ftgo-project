package com.ftgo.order.consumer;

import com.ftgo.order.events.KitchenRejectedEvent;
import com.ftgo.order.service.OrderSagaService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;

@Service
@Slf4j
@RequiredArgsConstructor
public class KitchenRejectedConsumer {

    private final OrderSagaService orderSagaService;

    @KafkaListener(topics = "ftgo.kitchen.ticket-rejected", groupId = "order-service-group")
    public void consumeKitchenRejected(KitchenRejectedEvent event) {

        log.info("Received KitchenRejectedEvent: {}", event);

        orderSagaService.cancelOrder(event.getOrderId());
    }
}