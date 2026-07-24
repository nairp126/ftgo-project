package com.ftgo.accounting.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.ftgo.accounting.dto.OrderCreatedEvent;
import java.util.HashMap;
import java.util.Map;
import lombok.extern.slf4j.Slf4j;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.support.serializer.JsonDeserializer;
import org.springframework.kafka.support.serializer.JsonSerializer;
import org.springframework.util.backoff.FixedBackOff;

/**
 * Kafka configuration for the Accounting Service.
 *
 * <p>Key design decisions:
 * <ul>
 *   <li>Manual acknowledgment: offsets committed only after successful
 *       processing; failed messages are retried automatically.</li>
 *   <li>Dead Letter Topic (DLT): after maxRetries, the
 *       message is forwarded to order.created.DLT for manual replay.</li>
 *   <li>Producer acks=all: ensures messages are written to all replicas.</li>
 * </ul>
 */
@Configuration
@EnableKafka
@Slf4j
public class KafkaConfig {

    /**
     * Default number of retries for Kafka producer.
     */
    private static final int PRODUCER_RETRIES = 3;

    /**
     * Default concurrency for Kafka consumer.
     */
    private static final int CONSUMER_CONCURRENCY = 3;

    /**
     * Kafka bootstrap servers.
     */
    @Value("${spring.kafka.bootstrap-servers:localhost:9092}")
    private String bootstrapServers;

    /**
     * Consumer group ID for the Accounting Service.
     */
    @Value("${spring.kafka.consumer.group-id:ftgo-accounting-service}")
    private String consumerGroupId;

    /**
     * Maximum number of retries for failed messages.
     */
    @Value("${ftgo.kafka.max-retries:3}")
    private int maxRetries;

    /**
     * Interval in milliseconds between retries.
     */
    @Value("${ftgo.kafka.retry-interval-ms:1000}")
    private long retryIntervalMs;

    /**
     * Creates the producer factory for Kafka.
     *
     * @return the producer factory
     */
    @Bean
    public ProducerFactory<String, Object> producerFactory() {
        final Map<String, Object> config = new HashMap<>();
        config.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        config.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        config.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                JsonSerializer.class);
        config.put(ProducerConfig.ACKS_CONFIG, "all");
        config.put(ProducerConfig.RETRIES_CONFIG, PRODUCER_RETRIES);
        config.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        return new DefaultKafkaProducerFactory<>(config);
    }

    /**
     * Creates the Kafka template for sending messages.
     *
     * @return the Kafka template
     */
    @Bean
    public KafkaTemplate<String, Object> kafkaTemplate() {
        return new KafkaTemplate<>(producerFactory());
    }

    /**
     * Creates the consumer factory for OrderCreatedEvent.
     *
     * @return the consumer factory
     */
    @Bean
    public ConsumerFactory<String, OrderCreatedEvent>
            orderCreatedConsumerFactory() {
        final Map<String, Object> config = new HashMap<>();
        config.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        config.put(ConsumerConfig.GROUP_ID_CONFIG, consumerGroupId);
        config.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        config.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

        final JsonDeserializer<OrderCreatedEvent> deserializer =
                new JsonDeserializer<>(OrderCreatedEvent.class, objectMapper());
        deserializer.addTrustedPackages("com.ftgo.*");

        return new DefaultKafkaConsumerFactory<>(config,
                new StringDeserializer(), deserializer);
    }

    /**
     * Creates the listener container factory for OrderCreatedEvent.
     *
     * @return the listener container factory
     */
    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
            orderCreatedListenerContainerFactory() {

        final ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
                factory = new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(orderCreatedConsumerFactory());

        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.MANUAL_IMMEDIATE);

        final DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate());
        final DefaultErrorHandler errorHandler = new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(retryIntervalMs, maxRetries)
        );
        factory.setCommonErrorHandler(errorHandler);

        factory.setConcurrency(CONSUMER_CONCURRENCY);

        return factory;
    }

    /**
     * Creates the Jackson object mapper for JSON serialization.
     *
     * @return the object mapper
     */
    @Bean
    public ObjectMapper objectMapper() {
        final ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        return mapper;
    }
}
