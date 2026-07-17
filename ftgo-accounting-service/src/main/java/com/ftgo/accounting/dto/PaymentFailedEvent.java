package com.ftgo.accounting.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * Outbound event DTO published to the {@code payment.failed} Kafka topic.
 *
 * <p>Consumed by the Order Service (Saga orchestrator) to signal that payment
 * authorization was declined.  The orchestrator must abort the create-order Saga
 * and issue compensating transactions to any prior completed steps (e.g. releasing
 * a kitchen ticket if one was already created).
 *
 * <p>Event schema (JSON):
 * <pre>
 * {
 *   "orderId":     12345,
 *   "consumerId":  67890,
 *   "amount":      49.99,
 *   "reason":      "INSUFFICIENT_FUNDS",
 *   "failedAt":    "2024-01-15T10:30:01Z"
 * }
 * </pre>
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PaymentFailedEvent {

    @JsonProperty("orderId")
    private Long orderId;

    @JsonProperty("consumerId")
    private Long consumerId;

    @JsonProperty("amount")
    private BigDecimal amount;

    @JsonProperty("reason")
    private String reason;

    @JsonProperty("failedAt")
    private Instant failedAt;
}
