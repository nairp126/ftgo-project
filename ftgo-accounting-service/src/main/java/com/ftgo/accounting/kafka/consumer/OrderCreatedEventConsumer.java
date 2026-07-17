package com.ftgo.accounting.kafka.consumer;

import com.ftgo.accounting.dto.OrderCreatedEvent;
import com.ftgo.accounting.service.AccountingService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

/**
 * Kafka consumer that listens to the {@code order.created} topic.
 *
 * <p>This consumer is the entry point of the Accounting Service's participation
 * in the create-order Saga.  It receives {@link OrderCreatedEvent} messages and
 * delegates processing to {@link AccountingService}.
 *
 * <h2>Consumer Group</h2>
 * <p>Consumer group ID {@code ftgo-accounting-service} ensures this service gets its
 * own independent offset tracking.  Multiple replicas of this service share the group,
 * enabling horizontal scaling with partition-based parallelism.
 *
 * <h2>Manual Acknowledgment</h2>
 * <p>Acknowledgment is manual ({@code AckMode.MANUAL_IMMEDIATE}) so that:
 * <ul>
 *   <li>On successful processing, the offset is committed.</li>
 *   <li>On processing failure, the offset is NOT committed — Kafka will re-deliver
 *       the message.  The {@link AccountingService#processOrderCreated} method's
 *       idempotency guard ensures safe reprocessing.</li>
 * </ul>
 *
 * <h2>Dead Letter Queue (DLQ)</h2>
 * <p>After a configurable number of retries ({@code ftgo.kafka.max-retries}), Spring Kafka's
 * {@code DeadLetterPublishingRecoverer} forwards the message to {@code order.created.DLT}
 * for manual inspection.  This is configured in {@link com.ftgo.accounting.config.KafkaConfig}.
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class OrderCreatedEventConsumer {

    private final AccountingService accountingService;

    /**
     * Listens for {@link OrderCreatedEvent} on the {@code order.created} topic.
     *
     * @param event           the deserialized event payload
     * @param partition        the Kafka partition the message arrived on (for debugging)
     * @param offset           the Kafka offset (for debugging and DLQ correlation)
     * @param acknowledgment   manual acknowledgment handle
     */
    @KafkaListener(
            topics = "${ftgo.kafka.topics.order-created:order.created}",
            groupId = "${spring.kafka.consumer.group-id:ftgo-accounting-service}",
            containerFactory = "orderCreatedListenerContainerFactory"
    )
    public void onOrderCreated(
            @Payload OrderCreatedEvent event,
            @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
            @Header(KafkaHeaders.OFFSET) long offset,
            Acknowledgment acknowledgment) {

        log.info("Received OrderCreated: orderId={}, consumerId={}, amount={}, partition={}, offset={}",
                event.getOrderId(), event.getConsumerId(), event.getOrderTotal(), partition, offset);

        try {
            accountingService.processOrderCreated(event);
            acknowledgment.acknowledge();
            log.info("Successfully processed OrderCreated for orderId={}", event.getOrderId());
        } catch (Exception ex) {
            log.error("Error processing OrderCreated for orderId={}: {}", event.getOrderId(), ex.getMessage(), ex);
            // Do NOT acknowledge — Spring Kafka retry/DLQ mechanism will handle redelivery.
            throw ex;
        }
    }
}
