package com.ftgo.order.dto;

import com.ftgo.order.entity.OrderStatus;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.math.BigDecimal;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class GetOrderResponse {

    private Long id;

    private Long consumerId;

    private Long restaurantId;

    private OrderStatus status;

    private BigDecimal totalAmount;
}
