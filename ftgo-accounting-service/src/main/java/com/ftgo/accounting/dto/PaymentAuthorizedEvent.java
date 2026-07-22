package com.ftgo.accounting.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.math.BigDecimal;
import java.time.Instant;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Outbound event DTO published to the {@code payment.authorized} Kafka topic.
 *
 * <p>Consumed by the Order Service to signal that the payment
 * hold was successfully placed.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PaymentAuthorizedEvent {

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
     * Amount that was authorized.
     */
    @JsonProperty("authorizedAmount")
    private BigDecimal authorizedAmount;

    /**
     * Timestamp of authorization.
     */
    @JsonProperty("authorizedAt")
    private Instant authorizedAt;
}
