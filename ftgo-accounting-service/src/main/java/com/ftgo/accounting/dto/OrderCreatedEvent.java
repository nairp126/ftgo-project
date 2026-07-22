package com.ftgo.accounting.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.math.BigDecimal;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Inbound event DTO for the {@code order.created} Kafka topic.
 *
 * <p>Published by the Order Service when a new order is placed.
 * The Accounting Service consumes this to trigger payment authorization.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class OrderCreatedEvent {

    /**
     * Unique identifier of the order used as the idempotency key.
     */
    @JsonProperty("orderId")
    private Long orderId;

    /**
     * Identifier of the consumer placing the order.
     */
    @JsonProperty("consumerId")
    private Long consumerId;

    /**
     * Total monetary value of the order to authorize.
     */
    @JsonProperty("orderTotal")
    private BigDecimal orderTotal;
}
