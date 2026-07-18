package com.ftgo.restaurantservice.config;

import com.ftgo.restaurantservice.kafka.RestaurantKafkaProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafka;

@EnableKafka
@Configuration
@EnableConfigurationProperties(RestaurantKafkaProperties.class)
public class KafkaProducerConfig {
}
