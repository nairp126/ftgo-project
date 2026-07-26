package com.ftgo.restaurantservice.kafka;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.kafka")
public record RestaurantKafkaProperties(
        String menuUpdatedTopic
) {
}
