package com.ftgo.accounting.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * Outbound event DTO published to the {@code payment.authorized} Kafka topic.
 *
 * <p>Consumed by the Order Service (Saga orchestrator) to signal that the payment
 * hold was successfully placed.  The orchestrator can then proceed to the next
 * Saga step (e.g. creating a kitchen ticket).
 *
 * <p>Event schema (JSON):
 * <pre>
 * {
 *   "orderId":         12345,
 *   "consumerId":      67890,
 *   "authorizedAmount": 49.99,
 *   "authorizedAt":    "2024-01-15T10:30:00Z"
 * }
 * </pre>
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PaymentAuthorizedEvent {

    @JsonProperty("orderId")
    private Long orderId;

    @JsonProperty("consumerId")
    private Long consumerId;

    @JsonProperty("authorizedAmount")
    private BigDecimal authorizedAmount;

    @JsonProperty("authorizedAt")
    private Instant authorizedAt;
}
