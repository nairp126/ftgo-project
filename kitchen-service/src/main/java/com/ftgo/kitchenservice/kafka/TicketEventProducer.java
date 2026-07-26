package com.ftgo.kitchenservice.kafka;

import com.ftgo.kitchenservice.entity.KitchenTicket;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class TicketEventProducer {

    private final KafkaTemplate<String, Object> kafkaTemplate;
    private final KitchenKafkaProperties kafkaProperties;

    public void publishTicketCreated(KitchenTicket ticket) {
        TicketCreatedEvent event = new TicketCreatedEvent(
                UUID.randomUUID(),
                "TicketCreated",
                Instant.now(),
                ticket.getId(),
                ticket.getOrderId(),
                ticket.getRestaurantId(),
                ticket.getItems().stream()
                        .map(item -> new TicketItemEvent(
                                item.getMenuItemId(),
                                item.getName(),
                                item.getQuantity(),
                                item.getSpecialInstructions()
                        ))
                        .toList()
        );
        publish(ticket.getOrderId().toString(), event);
    }

    public void publishTicketRejected(UUID orderId, UUID restaurantId, String reason) {
        TicketRejectedEvent event = new TicketRejectedEvent(
                UUID.randomUUID(),
                "TicketRejected",
                Instant.now(),
                orderId,
                restaurantId,
                reason
        );
        publish(orderId.toString(), event);
    }

    private void publish(String key, Object event) {
        kafkaTemplate.send(kafkaProperties.ticketEventsTopic(), key, event)
                .whenComplete((result, exception) -> {
                    if (exception != null) {
                        log.error("Failed to publish kitchen event key={}", key, exception);
                    } else {
                        log.info(
                                "Published kitchen event type={} topic={} partition={} offset={}",
                                event.getClass().getSimpleName(),
                                result.getRecordMetadata().topic(),
                                result.getRecordMetadata().partition(),
                                result.getRecordMetadata().offset()
                        );
                    }
                });
    }
}
