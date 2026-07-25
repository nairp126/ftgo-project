package com.ftgo.order.publisher;

import com.ftgo.order.events.OrderApprovedEvent;
import lombok.RequiredArgsConstructor;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@RequiredArgsConstructor
@Service
public class OrderApprovedEventPublisher {

    private final KafkaTemplate<String, OrderApprovedEvent> kafkaTemplate;

    public void publishOrderApproved(OrderApprovedEvent event) {
        kafkaTemplate.send("ftgo.order.approved", event);
    }
}