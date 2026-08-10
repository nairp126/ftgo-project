package com.ftgo.order.consumer;

import com.ftgo.order.events.PaymentFailedEvent;
import com.ftgo.order.service.OrderSagaService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;

@Service
@Slf4j
@RequiredArgsConstructor
public class PaymentFailedConsumer {

    private final OrderSagaService orderSagaService;

    @KafkaListener(topics = "ftgo.accounting.payment-failed", groupId = "order-service-group")
    public void consumePaymentFailed(PaymentFailedEvent event) {

        log.info("Received PaymentFailedEvent: {}", event);

        orderSagaService.cancelOrder(event.getOrderId());
    }
}