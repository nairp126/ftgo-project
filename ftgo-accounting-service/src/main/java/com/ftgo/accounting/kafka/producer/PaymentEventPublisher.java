package com.ftgo.accounting.kafka.producer;

import com.ftgo.accounting.dto.PaymentAuthorizedEvent;
import com.ftgo.accounting.dto.PaymentFailedEvent;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

/**
 * Publishes payment events to Kafka topics consumed by the Order Service.
 *
 * <p>Topics:
 * <ul>
 *   <li>payment.authorized: happy path; orchestrator proceeds.</li>
 *   <li>payment.failed: orchestrator aborts Saga and compensates.</li>
 * </ul>
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class PaymentEventPublisher {

    /**
     * Kafka template for sending messages.
     */
    private final KafkaTemplate<String, Object> kafkaTemplate;

    /**
     * Topic name for authorized payments.
     */
    @Value("${ftgo.kafka.topics.payment-authorized:payment.authorized}")
    private String paymentAuthorizedTopic;

    /**
     * Topic name for failed payments.
     */
    @Value("${ftgo.kafka.topics.payment-failed:payment.failed}")
    private String paymentFailedTopic;

    /**
     * Publishes a PaymentAuthorizedEvent to the payment.authorized topic.
     * The Kafka message key is the orderId to ensure ordered delivery.
     *
     * @param event the authorization success event
     */
    public void publishPaymentAuthorized(final PaymentAuthorizedEvent event) {
        final String key = String.valueOf(event.getOrderId());
        log.info("Publishing PaymentAuthorized event to topic={} key={}",
                paymentAuthorizedTopic, key);
        kafkaTemplate.send(paymentAuthorizedTopic, key, event)
                .whenComplete((result, ex) -> {
                    if (ex != null) {
                        log.error("Failed to publish PaymentAuthorized "
                                + "for orderId={}: {}",
                                event.getOrderId(), ex.getMessage(), ex);
                    } else {
                        log.debug("PaymentAuthorized published successfully "
                                + "for orderId={}", event.getOrderId());
                    }
                });
    }

    /**
     * Publishes a PaymentFailedEvent to the payment.failed topic.
     *
     * @param event the authorization failure event
     */
    public void publishPaymentFailed(final PaymentFailedEvent event) {
        final String key = String.valueOf(event.getOrderId());
        log.info("Publishing PaymentFailed event to topic={} key={}",
                paymentFailedTopic, key);
        kafkaTemplate.send(paymentFailedTopic, key, event)
                .whenComplete((result, ex) -> {
                    if (ex != null) {
                        log.error("Failed to publish PaymentFailed "
                                + "for orderId={}: {}",
                                event.getOrderId(), ex.getMessage(), ex);
                    } else {
                        log.debug("PaymentFailed published successfully "
                                + "for orderId={}", event.getOrderId());
                    }
                });
    }
}
