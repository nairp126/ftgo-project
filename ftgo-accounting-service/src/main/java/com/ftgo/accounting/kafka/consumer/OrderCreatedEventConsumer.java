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
 * Kafka consumer that listens to the order.created topic.
 *
 * <p>This consumer is the entry point of the Accounting Service's participation
 * in the create-order Saga. It receives OrderCreatedEvent messages and
 * delegates processing to AccountingService.
 *
 * <h2>Consumer Group</h2>
 * <p>Consumer group ID ftgo-accounting-service ensures independent tracking.
 *
 * <h2>Manual Acknowledgment</h2>
 * <p>Acknowledgment is manual (AckMode.MANUAL_IMMEDIATE) so that:
 * <ul>
 *   <li>On successful processing, the offset is committed.</li>
 *   <li>On processing failure, the offset is NOT committed.</li>
 * </ul>
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class OrderCreatedEventConsumer {

    /**
     * The business logic service for accounting.
     */
    private final AccountingService accountingService;

    /**
     * Listens for OrderCreatedEvent on the order.created topic.
     *
     * @param event          the deserialized event payload
     * @param partition      the Kafka partition the message arrived on
     * @param offset         the Kafka offset
     * @param acknowledgment manual acknowledgment handle
     */
    @KafkaListener(
            topics = "${ftgo.kafka.topics.order-created:order.created}",
            groupId = "${spring.kafka.consumer.group-id:ftgo"
                    + "-accounting-service}",
            containerFactory = "orderCreatedListenerContainerFactory"
    )
    public void onOrderCreated(
            @Payload final OrderCreatedEvent event,
            @Header(KafkaHeaders.RECEIVED_PARTITION) final int partition,
            @Header(KafkaHeaders.OFFSET) final long offset,
            final Acknowledgment acknowledgment) {

        log.info("Received OrderCreated: orderId={}, amount={}, "
                + "partition={}, offset={}",
                event.getOrderId(), event.getOrderTotal(), partition, offset);

        try {
            accountingService.processOrderCreated(event);
            acknowledgment.acknowledge();
            log.info("Successfully processed OrderCreated for orderId={}",
                    event.getOrderId());
        } catch (Exception ex) {
            log.error("Error processing OrderCreated for orderId={}: {}",
                    event.getOrderId(), ex.getMessage(), ex);
            throw ex;
        }
    }
}
