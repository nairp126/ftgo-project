package com.ftgo.order.events;

import com.ftgo.order.entity.OrderStatus;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class PaymentApprovedEvent {

    private Long orderId;
    private Long consumerId;
    private Long restaurantId;
    private BigDecimal totalAmount;
    private OrderStatus status;
}