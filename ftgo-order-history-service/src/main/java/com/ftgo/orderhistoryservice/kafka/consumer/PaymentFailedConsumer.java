package com.ftgo.orderhistoryservice.kafka.consumer;

import com.ftgo.orderhistoryservice.kafka.dto.accounting.PaymentFailedEvent;
import com.ftgo.orderhistoryservice.service.OrderHistoryService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class PaymentFailedConsumer {

    private static final Logger log =
            LoggerFactory.getLogger(PaymentFailedConsumer.class);

    private final OrderHistoryService orderHistoryService;

    public PaymentFailedConsumer(OrderHistoryService orderHistoryService) {
        this.orderHistoryService = orderHistoryService;
    }

    @KafkaListener(
            topics = "${ftgo.kafka.topics.payment-failed}",
            groupId = "${spring.kafka.consumer.group-id}"
    )
    public void consume(PaymentFailedEvent event) {

        log.info("Received PaymentFailedEvent for orderId={}", event.getOrderId());

        orderHistoryService.handlePaymentFailed(event);
    }
}