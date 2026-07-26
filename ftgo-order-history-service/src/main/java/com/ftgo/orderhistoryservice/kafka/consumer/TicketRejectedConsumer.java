package com.ftgo.orderhistoryservice.kafka.consumer;

import com.ftgo.orderhistoryservice.kafka.dto.kitchen.TicketRejectedEvent;
import com.ftgo.orderhistoryservice.service.OrderHistoryService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class TicketRejectedConsumer {

    private static final Logger log =
            LoggerFactory.getLogger(TicketRejectedConsumer.class);

    private final OrderHistoryService orderHistoryService;

    public TicketRejectedConsumer(OrderHistoryService orderHistoryService) {
        this.orderHistoryService = orderHistoryService;
    }

    @KafkaListener(
            topics = "${ftgo.kafka.topics.ticket-rejected}",
            groupId = "${spring.kafka.consumer.group-id}"
    )
    public void consume(TicketRejectedEvent event) {

        log.info("Received TicketRejectedEvent for orderId={}", event.orderId());

        orderHistoryService.handleTicketRejected(event);
    }
}