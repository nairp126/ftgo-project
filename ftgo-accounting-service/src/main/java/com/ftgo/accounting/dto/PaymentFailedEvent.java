package com.ftgo.accounting.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.math.BigDecimal;
import java.time.Instant;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Outbound event DTO published to the {@code payment.failed} Kafka topic.
 *
 * <p>Consumed by the Order Service to signal that payment
 * authorization was declined.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PaymentFailedEvent {

    /**
     * Unique identifier of the order.
     */
    @JsonProperty("orderId")
    private Long orderId;

    /**
     * Identifier of the consumer placing the order.
     */
    @JsonProperty("consumerId")
    private Long consumerId;

    /**
     * Amount that failed authorization.
     */
    @JsonProperty("amount")
    private BigDecimal amount;

    /**
     * Reason for failure.
     */
    @JsonProperty("reason")
    private String reason;

    /**
     * Timestamp of failure.
     */
    @JsonProperty("failedAt")
    private Instant failedAt;
}
