package com.ftgo.restaurantservice.kafka;

import com.ftgo.restaurantservice.entity.MenuItem;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class MenuEventProducer {

    private final KafkaTemplate<String, MenuUpdatedEvent> kafkaTemplate;
    private final RestaurantKafkaProperties kafkaProperties;

    public void publishMenuUpdated(MenuItem menuItem, MenuChangeType changeType) {
        MenuUpdatedEvent event = new MenuUpdatedEvent(
                UUID.randomUUID(),
                "MenuUpdated",
                Instant.now(),
                changeType,
                menuItem.getRestaurant().getId(),
                menuItem.getId(),
                menuItem.getName(),
                menuItem.getDescription(),
                menuItem.getPrice(),
                menuItem.isAvailable(),
                menuItem.getCategory(),
                menuItem.getVersion()
        );

        String key = menuItem.getRestaurant().getId().toString();
        kafkaTemplate.send(kafkaProperties.menuUpdatedTopic(), key, event)
                .whenComplete((result, exception) -> {
                    if (exception != null) {
                        log.error("Failed to publish MenuUpdated event for menuItemId={}", menuItem.getId(), exception);
                    } else {
                        log.info(
                                "Published MenuUpdated event eventId={} changeType={} menuItemId={} topic={} partition={} offset={}",
                                event.eventId(),
                                event.changeType(),
                                event.menuItemId(),
                                result.getRecordMetadata().topic(),
                                result.getRecordMetadata().partition(),
                                result.getRecordMetadata().offset()
                        );
                    }
                });
    }
}
