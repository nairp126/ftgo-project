package com.ftgo.accounting.domain;

import jakarta.persistence.*;
import lombok.*;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * Records an individual payment authorization attempt for an order.
 *
 * <p>This table provides the idempotency guarantee for at-least-once Kafka delivery:
 * before processing any {@code OrderCreated} event, the service checks whether a
 * {@link PaymentAuthorization} already exists for that {@code orderId}.  If it does,
 * the existing outcome is re-published and the duplicate event is discarded — no
 * double-charge can occur.
 *
 * <p>Status lifecycle:
 * <pre>
 *   PENDING → AUTHORIZED  (happy path)
 *   PENDING → DECLINED    (insufficient funds)
 *   AUTHORIZED → REVERSED (compensating transaction on saga rollback)
 * </pre>
 */
@Entity
@Table(
    name = "payment_authorizations",
    uniqueConstraints = @UniqueConstraint(name = "uq_order_id", columnNames = "order_id")
)
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PaymentAuthorization {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /**
     * Globally unique order identifier (from Order Service).
     * The unique constraint on this column enforces idempotency at the DB level
     * as a safety net behind the application-level check.
     */
    @Column(name = "order_id", nullable = false, updatable = false, unique = true)
    private Long orderId;

    @Column(name = "consumer_id", nullable = false, updatable = false)
    private Long consumerId;

    @Column(name = "amount", nullable = false, precision = 12, scale = 2)
    private BigDecimal amount;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private AuthorizationStatus status;

    /** Reason for decline, populated only when status = DECLINED. */
    @Column(name = "decline_reason", length = 255)
    private String declineReason;

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

    public boolean isAuthorized() {
        return AuthorizationStatus.AUTHORIZED.equals(status);
    }

    /**
     * Authorization outcome states for the payment Saga step.
     */
    public enum AuthorizationStatus {
        /** Transient state during processing (not persisted in normal flow). */
        PENDING,
        /** Payment hold successfully placed on consumer account. */
        AUTHORIZED,
        /** Authorization declined (e.g. insufficient funds). */
        DECLINED,
        /** Previously authorized hold was released (saga compensating transaction). */
        REVERSED
    }
}
