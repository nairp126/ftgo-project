package com.ftgo.orderhistoryservice.kafka.consumer;

import com.ftgo.orderhistoryservice.kafka.dto.accounting.PaymentAuthorizedEvent;
import com.ftgo.orderhistoryservice.service.OrderHistoryService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class PaymentAuthorizedConsumer {

    private static final Logger log =
            LoggerFactory.getLogger(PaymentAuthorizedConsumer.class);

    private final OrderHistoryService orderHistoryService;

    public PaymentAuthorizedConsumer(OrderHistoryService orderHistoryService) {
        this.orderHistoryService = orderHistoryService;
    }

    @KafkaListener(
            topics = "${ftgo.kafka.topics.payment-authorized}",
            groupId = "${spring.kafka.consumer.group-id}"
    )
    public void consume(PaymentAuthorizedEvent event) {

        log.info("Received PaymentAuthorizedEvent for orderId={}", event.getOrderId());

        orderHistoryService.handlePaymentAuthorized(event);
    }
}