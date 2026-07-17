package com.ftgo.accounting.service;

import com.ftgo.accounting.domain.ConsumerAccount;
import com.ftgo.accounting.domain.PaymentAuthorization;
import com.ftgo.accounting.domain.PaymentAuthorization.AuthorizationStatus;
import com.ftgo.accounting.dto.OrderCreatedEvent;
import com.ftgo.accounting.dto.PaymentAuthorizedEvent;
import com.ftgo.accounting.dto.PaymentFailedEvent;
import com.ftgo.accounting.kafka.producer.PaymentEventPublisher;
import com.ftgo.accounting.repository.ConsumerAccountRepository;
import com.ftgo.accounting.repository.PaymentAuthorizationRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.Optional;

/**
 * Core business logic for the Accounting Service.
 *
 * <h2>Saga Participant Role</h2>
 * <p>This service does NOT orchestrate — it only reacts to commands (events) from
 * the Order Service (the Saga orchestrator).  When it receives an {@code OrderCreated}
 * event it:
 * <ol>
 *   <li>Checks idempotency — if the order was already processed, re-publishes the result.</li>
 *   <li>Looks up the consumer's account.</li>
 *   <li>Attempts to place a credit hold for the order total.</li>
 *   <li>Persists the {@link PaymentAuthorization} record.</li>
 *   <li>Publishes either {@code payment.authorized} or {@code payment.failed}.</li>
 * </ol>
 *
 * <h2>Idempotency</h2>
 * <p>Kafka delivers messages at-least-once.  The unique constraint on
 * {@code payment_authorizations.order_id} combined with the application-level
 * {@code findByOrderId} check ensures that duplicate {@code OrderCreated} deliveries
 * produce no additional side-effects.
 *
 * <h2>Compensating Transaction</h2>
 * <p>If a later Saga step fails (e.g. Kitchen declines), the Order Service issues a
 * compensating command.  {@link #reverseAuthorization(Long)} handles this by restoring
 * the credit hold to the consumer's account.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class AccountingService {

    private final ConsumerAccountRepository accountRepository;
    private final PaymentAuthorizationRepository authorizationRepository;
    private final PaymentEventPublisher eventPublisher;

    /**
     * Processes an {@code OrderCreated} event: authorizes payment or declines.
     *
     * <p>This method is the primary entry point called by the Kafka consumer.
     * It is fully transactional — the DB write and the Kafka publish are both
     * attempted within the same logical unit (Kafka publish happens after commit
     * via the publisher pattern; Kafka outbox/transactional producer is out of scope
     * for this implementation but noted in the ADR).
     *
     * @param event the inbound {@code OrderCreated} event
     */
    @Transactional
    public void processOrderCreated(OrderCreatedEvent event) {
        log.info("Processing OrderCreated event: orderId={}, consumerId={}, amount={}",
                event.getOrderId(), event.getConsumerId(), event.getOrderTotal());

        // ── Idempotency check ──────────────────────────────────────────────────
        Optional<PaymentAuthorization> existing =
                authorizationRepository.findByOrderId(event.getOrderId());

        if (existing.isPresent()) {
            log.warn("Duplicate OrderCreated event detected for orderId={}. " +
                    "Replaying existing result without reprocessing.", event.getOrderId());
            replayResult(existing.get(), event);
            return;
        }

        // ── Look up consumer account ───────────────────────────────────────────
        Optional<ConsumerAccount> accountOpt =
                accountRepository.findById(event.getConsumerId());

        if (accountOpt.isEmpty()) {
            log.error("Consumer account not found for consumerId={}. Declining payment for orderId={}",
                    event.getConsumerId(), event.getOrderId());
            persistAndPublishDecline(event, "CONSUMER_ACCOUNT_NOT_FOUND");
            return;
        }

        ConsumerAccount account = accountOpt.get();

        // ── Attempt authorization ──────────────────────────────────────────────
        boolean authorized = account.authorize(event.getOrderTotal());

        if (authorized) {
            accountRepository.save(account);

            PaymentAuthorization authorization = PaymentAuthorization.builder()
                    .orderId(event.getOrderId())
                    .consumerId(event.getConsumerId())
                    .amount(event.getOrderTotal())
                    .status(AuthorizationStatus.AUTHORIZED)
                    .build();
            authorizationRepository.save(authorization);

            log.info("Payment authorized for orderId={}, amount={}", event.getOrderId(), event.getOrderTotal());

            eventPublisher.publishPaymentAuthorized(PaymentAuthorizedEvent.builder()
                    .orderId(event.getOrderId())
                    .consumerId(event.getConsumerId())
                    .authorizedAmount(event.getOrderTotal())
                    .authorizedAt(Instant.now())
                    .build());
        } else {
            log.warn("Payment declined for orderId={} — insufficient funds. " +
                    "Available: {}, Required: {}", event.getOrderId(),
                    account.getAvailableCredit(), event.getOrderTotal());
            persistAndPublishDecline(event, "INSUFFICIENT_FUNDS");
        }
    }

    /**
     * Compensating transaction: reverse a previously authorized payment hold.
     *
     * <p>Called when the Order Service determines that the create-order Saga has
     * failed at a later step (e.g. Kitchen rejected the ticket) and instructs
     * the Accounting Service to release the credit hold.
     *
     * @param orderId the order whose authorization should be reversed
     */
    @Transactional
    public void reverseAuthorization(Long orderId) {
        log.info("Reversing payment authorization for orderId={}", orderId);

        PaymentAuthorization auth = authorizationRepository.findByOrderId(orderId)
                .orElseThrow(() -> new IllegalStateException(
                        "No authorization record found for orderId=" + orderId));

        if (!AuthorizationStatus.AUTHORIZED.equals(auth.getStatus())) {
            log.warn("Cannot reverse authorization for orderId={} — status is {}", orderId, auth.getStatus());
            return;
        }

        ConsumerAccount account = accountRepository.findById(auth.getConsumerId())
                .orElseThrow(() -> new IllegalStateException(
                        "Consumer account missing for consumerId=" + auth.getConsumerId()));

        account.releaseAuthorization(auth.getAmount());
        accountRepository.save(account);

        auth.setStatus(AuthorizationStatus.REVERSED);
        authorizationRepository.save(auth);

        log.info("Authorization reversed for orderId={}, amount={} returned to consumerId={}",
                orderId, auth.getAmount(), auth.getConsumerId());
    }

    // ─── Private helpers ──────────────────────────────────────────────────────

    private void persistAndPublishDecline(OrderCreatedEvent event, String reason) {
        PaymentAuthorization authorization = PaymentAuthorization.builder()
                .orderId(event.getOrderId())
                .consumerId(event.getConsumerId())
                .amount(event.getOrderTotal())
                .status(AuthorizationStatus.DECLINED)
                .declineReason(reason)
                .build();
        authorizationRepository.save(authorization);

        eventPublisher.publishPaymentFailed(PaymentFailedEvent.builder()
                .orderId(event.getOrderId())
                .consumerId(event.getConsumerId())
                .amount(event.getOrderTotal())
                .reason(reason)
                .failedAt(Instant.now())
                .build());
    }

    private void replayResult(PaymentAuthorization existing, OrderCreatedEvent event) {
        if (existing.isAuthorized()) {
            eventPublisher.publishPaymentAuthorized(PaymentAuthorizedEvent.builder()
                    .orderId(existing.getOrderId())
                    .consumerId(existing.getConsumerId())
                    .authorizedAmount(existing.getAmount())
                    .authorizedAt(existing.getCreatedAt())
                    .build());
        } else {
            eventPublisher.publishPaymentFailed(PaymentFailedEvent.builder()
                    .orderId(existing.getOrderId())
                    .consumerId(existing.getConsumerId())
                    .amount(existing.getAmount())
                    .reason(existing.getDeclineReason())
                    .failedAt(existing.getCreatedAt())
                    .build());
        }
    }
}
