package com.ftgo.kitchenservice.kafka;

import com.ftgo.kitchenservice.service.KitchenMenuService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Slf4j
@Component
@RequiredArgsConstructor
public class MenuUpdatedConsumer {

    private final KitchenMenuService kitchenMenuService;

    @KafkaListener(
            topics = "${app.kafka.menu-updated-topic}",
            groupId = "${spring.kafka.consumer.group-id}",
            containerFactory = "kafkaListenerContainerFactory"
    )
    public void consume(MenuUpdatedEvent event) {
        log.info("Received MenuUpdated event menuItemId={} changeType={}", event.menuItemId(), event.changeType());
        kitchenMenuService.applyMenuUpdated(event);
    }
}
