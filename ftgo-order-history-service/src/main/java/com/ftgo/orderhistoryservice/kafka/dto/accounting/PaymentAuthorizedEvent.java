package com.ftgo.orderhistoryservice.kafka.dto.accounting;

import java.math.BigDecimal;
import java.time.Instant;

public class PaymentAuthorizedEvent {

    private Long orderId;
    private Long consumerId;
    private BigDecimal authorizedAmount;
    private Instant authorizedAt;

    public PaymentAuthorizedEvent() {
    }

    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    public Long getConsumerId() {
        return consumerId;
    }

    public void setConsumerId(Long consumerId) {
        this.consumerId = consumerId;
    }

    public BigDecimal getAuthorizedAmount() {
        return authorizedAmount;
    }

    public void setAuthorizedAmount(BigDecimal authorizedAmount) {
        this.authorizedAmount = authorizedAmount;
    }

    public Instant getAuthorizedAt() {
        return authorizedAt;
    }

    public void setAuthorizedAt(Instant authorizedAt) {
        this.authorizedAt = authorizedAt;
    }
}