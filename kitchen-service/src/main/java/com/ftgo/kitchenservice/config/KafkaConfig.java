package com.ftgo.kitchenservice.config;

import com.ftgo.kitchenservice.kafka.KitchenKafkaProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.support.converter.JsonMessageConverter;

@EnableKafka
@Configuration
@EnableConfigurationProperties(KitchenKafkaProperties.class)
public class KafkaConfig {

    @Bean
    public JsonMessageConverter jsonMessageConverter() {
        return new JsonMessageConverter();
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, Object> kafkaListenerContainerFactory(
            ConsumerFactory<String, Object> consumerFactory,
            JsonMessageConverter jsonMessageConverter
    ) {
        ConcurrentKafkaListenerContainerFactory<String, Object> factory =
                new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(consumerFactory);
        factory.setRecordMessageConverter(jsonMessageConverter);
        factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.RECORD);
        return factory;
    }
}
