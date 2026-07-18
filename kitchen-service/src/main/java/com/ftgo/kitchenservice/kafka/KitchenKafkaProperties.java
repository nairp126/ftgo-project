package com.ftgo.kitchenservice.kafka;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.kafka")
public record KitchenKafkaProperties(
        String orderCreatedTopic,
        String menuUpdatedTopic,
        String ticketEventsTopic
) {
}
