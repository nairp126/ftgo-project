package com.ftgo.order.events;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class TicketCreatedEvent {

    private Long orderId;
    private Long consumerId;
    private Long restaurantId;
    private BigDecimal totalAmount;
}