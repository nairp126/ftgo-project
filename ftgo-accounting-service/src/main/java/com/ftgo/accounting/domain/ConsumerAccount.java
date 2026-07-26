package com.ftgo.accounting.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * Aggregate root representing a consumer's account balance.
 *
 * <p><strong>Database-per-service</strong>: no other FTGO service reads this.
 * The {@code consumer_accounts} table lives in the Accounting Service schema.
 *
 * <p><strong>PCI note</strong>: actual card numbers are NOT stored here.
 * Only the credit balance / available credit is tracked.
 */
@Entity
@Table(name = "consumer_accounts")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ConsumerAccount {

    /**
     * Precision for monetary amounts.
     */
    private static final int PRECISION = 12;

    /**
     * Unique identifier for the consumer account.
     */
    @Id
    @Column(name = "consumer_id", nullable = false, updatable = false)
    private Long consumerId;

    /**
     * Available credit / balance the consumer can spend.
     */
    @Column(name = "available_credit", nullable = false,
            precision = PRECISION, scale = 2)
    private BigDecimal availableCredit;

    /**
     * Timestamp when the account was created.
     */
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    /**
     * Timestamp when the account was last updated.
     */
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    /**
     * JPA lifecycle callback to set creation timestamps.
     */
    @PrePersist
    private void onCreate() {
        createdAt = Instant.now();
        updatedAt = Instant.now();
    }

    /**
     * JPA lifecycle callback to update modification timestamp.
     */
    @PreUpdate
    private void onUpdate() {
        updatedAt = Instant.now();
    }

    /**
     * Attempt to place a hold (deduct) on available credit.
     *
     * @param amount the amount to authorize
     * @return true if the account has sufficient credit
     */
    public boolean authorize(final BigDecimal amount) {
        if (availableCredit.compareTo(amount) >= 0) {
            availableCredit = availableCredit.subtract(amount);
            return true;
        }
        return false;
    }

    /**
     * Compensating transaction: release an authorization hold.
     *
     * @param amount the amount to release back to available credit
     */
    public void releaseAuthorization(final BigDecimal amount) {
        availableCredit = availableCredit.add(amount);
    }
}
