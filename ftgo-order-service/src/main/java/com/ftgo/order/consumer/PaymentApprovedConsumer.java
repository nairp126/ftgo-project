package com.ftgo.order.consumer;

import com.ftgo.order.entity.Order;
import com.ftgo.order.events.PaymentApprovedEvent;
import com.ftgo.order.repository.OrderRepository;
import com.ftgo.order.service.OrderSagaService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;

@Service
@Slf4j
@RequiredArgsConstructor
public class PaymentApprovedConsumer {

        private final OrderRepository orderRepository;
        private final OrderSagaService orderSagaService;

        @KafkaListener(topics = "ftgo.accounting.payment-authorized", groupId = "order-service-group")
        public void consumePaymentApproved(PaymentApprovedEvent event) {

                log.info("Received PaymentApprovedEvent: {}", event);

                Order order = orderRepository.findById(event.getOrderId())
                                .orElseThrow(() -> new IllegalArgumentException(
                                                "Order not found: " + event.getOrderId()));

                order.setPaymentApproved(true);

                orderRepository.save(order);

                orderSagaService.tryApprove(order.getId());
        }
}