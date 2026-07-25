package com.ftgo.order.publisher;

import com.ftgo.order.events.OrderCancelledEvent;
import lombok.RequiredArgsConstructor;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class OrderCancelledEventPublisher {

    private final KafkaTemplate<String, OrderCancelledEvent> kafkaTemplate;

    public void publishOrderCancelled(OrderCancelledEvent event) {
        kafkaTemplate.send("ftgo.order.cancelled", event);
    }
}