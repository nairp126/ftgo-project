package com.ftgo.accounting.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.math.BigDecimal;
import java.time.Instant;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * Records an individual payment authorization attempt for an order.
 *
 * <p>This table provides the idempotency guarantee for at-least-once Kafka
 * delivery: before processing any OrderCreated event, the service checks
 * whether a PaymentAuthorization already exists for that orderId. If it does,
 * the existing outcome is re-published and the duplicate event is discarded.
 *
 * <p>Status lifecycle:
 * <pre>
 *   PENDING - AUTHORIZED  (happy path)
 *   PENDING - DECLINED    (insufficient funds)
 *   AUTHORIZED - REVERSED (compensating transaction on saga rollback)
 * </pre>
 */
@Entity
@Table(
    name = "payment_authorizations",
    uniqueConstraints = @UniqueConstraint(name = "uq_order_id",
            columnNames = "order_id")
)
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PaymentAuthorization {

    /**
     * Precision for monetary amounts.
     */
    private static final int PRECISION = 12;

    /**
     * Maximum length for status column.
     */
    private static final int STATUS_LENGTH = 20;

    /**
     * Maximum length for decline reason column.
     */
    private static final int REASON_LENGTH = 255;

    /**
     * Unique identifier for the payment authorization.
     */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /**
     * Globally unique order identifier (from Order Service).
     */
    @Column(name = "order_id", nullable = false, updatable = false,
            unique = true)
    private Long orderId;

    /**
     * Consumer identifier who owns the account.
     */
    @Column(name = "consumer_id", nullable = false, updatable = false)
    private Long consumerId;

    /**
     * Amount of the payment authorization.
     */
    @Column(name = "amount", nullable = false,
            precision = PRECISION, scale = 2)
    private BigDecimal amount;

    /**
     * Current status of the payment authorization.
     */
    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = STATUS_LENGTH)
    private AuthorizationStatus status;

    /**
     * Reason for decline, populated only when status is DECLINED.
     */
    @Column(name = "decline_reason", length = REASON_LENGTH)
    private String declineReason;

    /**
     * Timestamp when the authorization was created.
     */
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    /**
     * Timestamp when the authorization was last updated.
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
     * Checks if the payment is successfully authorized.
     *
     * @return true if authorized, false otherwise
     */
    public boolean isAuthorized() {
        return AuthorizationStatus.AUTHORIZED.equals(status);
    }

    /**
     * Authorization outcome states for the payment Saga step.
     */
    public enum AuthorizationStatus {
        /** Transient state during processing. */
        PENDING,
        /** Payment hold successfully placed on consumer account. */
        AUTHORIZED,
        /** Authorization declined (e.g. insufficient funds). */
        DECLINED,
        /** Previously authorized hold was released. */
        REVERSED
    }
}
