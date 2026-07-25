package com.ftgo.orderhistoryservice.kafka.consumer;

import com.ftgo.orderhistoryservice.kafka.dto.kitchen.TicketCreatedEvent;
import com.ftgo.orderhistoryservice.service.OrderHistoryService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class TicketCreatedConsumer {

    private static final Logger log =
            LoggerFactory.getLogger(TicketCreatedConsumer.class);

    private final OrderHistoryService orderHistoryService;

    public TicketCreatedConsumer(OrderHistoryService orderHistoryService) {
        this.orderHistoryService = orderHistoryService;
    }

    @KafkaListener(
            topics = "${ftgo.kafka.topics.ticket-created}",
            groupId = "${spring.kafka.consumer.group-id}"
    )
    public void consume(TicketCreatedEvent event) {

        log.info("Received TicketCreatedEvent for orderId={}", event.orderId());

        orderHistoryService.handleTicketCreated(event);
    }
}