package com.ftgo.accounting.domain;

import jakarta.persistence.*;
import lombok.*;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * Aggregate root representing a consumer's account balance held by the Accounting Service.
 *
 * <p><strong>Database-per-service</strong>: no other FTGO service reads or writes this table.
 * The {@code consumer_accounts} table lives in the Accounting Service's own Postgres schema.
 *
 * <p><strong>PCI note</strong>: actual card numbers / payment tokens are NOT stored here.
 * Only the credit balance / available credit is tracked.  Real card data would be held
 * by a PCI-certified vault (e.g. Stripe, Braintree). This keeps PCI DSS scope minimal.
 */
@Entity
@Table(name = "consumer_accounts")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ConsumerAccount {

    @Id
    @Column(name = "consumer_id", nullable = false, updatable = false)
    private Long consumerId;

    /**
     * Available credit / balance the consumer can spend.
     * In production this would represent a pre-authorized credit limit or wallet balance.
     * Mock implementation: starts at a configurable default (e.g. $500).
     */
    @Column(name = "available_credit", nullable = false, precision = 12, scale = 2)
    private BigDecimal availableCredit;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @PrePersist
    private void onCreate() {
        createdAt = Instant.now();
        updatedAt = Instant.now();
    }

    @PreUpdate
    private void onUpdate() {
        updatedAt = Instant.now();
    }

    /**
     * Attempt to place a hold (deduct) on available credit.
     *
     * @param amount the amount to authorize
     * @return {@code true} if the account has sufficient credit and the hold was applied;
     *         {@code false} otherwise (insufficient funds)
     */
    public boolean authorize(BigDecimal amount) {
        if (availableCredit.compareTo(amount) >= 0) {
            availableCredit = availableCredit.subtract(amount);
            return true;
        }
        return false;
    }

    /**
     * Compensating transaction: release a previously placed authorization hold.
     * Called when a later Saga step fails and the Order Service issues a
     * reverse/cancel-payment-authorization command.
     *
     * @param amount the amount to release back to available credit
     */
    public void releaseAuthorization(BigDecimal amount) {
        availableCredit = availableCredit.add(amount);
    }
}
