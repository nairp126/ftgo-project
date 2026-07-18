package com.ftgo.kitchenservice.kafka;

import com.ftgo.kitchenservice.service.KitchenTicketService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Slf4j
@Component
@RequiredArgsConstructor
public class OrderCreatedConsumer {

    private final KitchenTicketService kitchenTicketService;

    @KafkaListener(
            topics = "${app.kafka.order-created-topic}",
            groupId = "${spring.kafka.consumer.group-id}",
            containerFactory = "kafkaListenerContainerFactory"
    )
    public void consume(OrderCreatedEvent event) {
        log.info("Received OrderCreated event orderId={} restaurantId={}", event.orderId(), event.restaurantId());
        kitchenTicketService.handleOrderCreated(event);
    }
}
