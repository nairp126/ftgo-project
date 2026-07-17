package com.ftgo.accounting.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * Inbound event DTO for the {@code order.created} Kafka topic.
 *
 * <p>Published by the Order Service (Saga orchestrator) when a new order is placed.
 * The Accounting Service consumes this to trigger payment authorization.
 *
 * <p>Event schema (JSON):
 * <pre>
 * {
 *   "orderId":     12345,
 *   "consumerId":  67890,
 *   "orderTotal":  49.99
 * }
 * </pre>
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class OrderCreatedEvent {

    /** Unique identifier of the order — used as the idempotency key. */
    @JsonProperty("orderId")
    private Long orderId;

    /** Identifier of the consumer placing the order. */
    @JsonProperty("consumerId")
    private Long consumerId;

    /** Total monetary value of the order to authorize. */
    @JsonProperty("orderTotal")
    private BigDecimal orderTotal;
}
