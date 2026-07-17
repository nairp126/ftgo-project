package com.ftgo.accounting.kafka.producer;

import com.ftgo.accounting.dto.PaymentAuthorizedEvent;
import com.ftgo.accounting.dto.PaymentFailedEvent;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

/**
 * Publishes payment events to Kafka topics consumed by the Order Service (Saga orchestrator).
 *
 * <p>Topics:
 * <ul>
 *   <li>{@code payment.authorized} — happy path; orchestrator proceeds to next Saga step</li>
 *   <li>{@code payment.failed} — orchestrator aborts Saga and issues compensating transactions</li>
 * </ul>
 *
 * <p><strong>At-least-once delivery</strong>: Spring Kafka with {@code acks=all} and
 * {@code retries} configured ensures messages are not lost on transient broker failures.
 * The consumer side (Order Service) must be idempotent for the same reason.
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class PaymentEventPublisher {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    @Value("${ftgo.kafka.topics.payment-authorized:payment.authorized}")
    private String paymentAuthorizedTopic;

    @Value("${ftgo.kafka.topics.payment-failed:payment.failed}")
    private String paymentFailedTopic;

    /**
     * Publishes a {@link PaymentAuthorizedEvent} to the {@code payment.authorized} topic.
     * The Kafka message key is the {@code orderId} (as String) to ensure ordered delivery
     * for the same order within a partition.
     *
     * @param event the authorization success event
     */
    public void publishPaymentAuthorized(PaymentAuthorizedEvent event) {
        String key = String.valueOf(event.getOrderId());
        log.info("Publishing PaymentAuthorized event to topic={} key={}", paymentAuthorizedTopic, key);
        kafkaTemplate.send(paymentAuthorizedTopic, key, event)
                .whenComplete((result, ex) -> {
                    if (ex != null) {
                        log.error("Failed to publish PaymentAuthorized for orderId={}: {}",
                                event.getOrderId(), ex.getMessage(), ex);
                    } else {
                        log.debug("PaymentAuthorized published successfully for orderId={}", event.getOrderId());
                    }
                });
    }

    /**
     * Publishes a {@link PaymentFailedEvent} to the {@code payment.failed} topic.
     *
     * @param event the authorization failure event
     */
    public void publishPaymentFailed(PaymentFailedEvent event) {
        String key = String.valueOf(event.getOrderId());
        log.info("Publishing PaymentFailed event to topic={} key={}", paymentFailedTopic, key);
        kafkaTemplate.send(paymentFailedTopic, key, event)
                .whenComplete((result, ex) -> {
                    if (ex != null) {
                        log.error("Failed to publish PaymentFailed for orderId={}: {}",
                                event.getOrderId(), ex.getMessage(), ex);
                    } else {
                        log.debug("PaymentFailed published successfully for orderId={}", event.getOrderId());
                    }
                });
    }
}
