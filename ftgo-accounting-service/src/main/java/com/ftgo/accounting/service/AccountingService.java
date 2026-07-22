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
import java.time.Instant;
import java.util.Optional;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Core business logic for the Accounting Service.
 *
 * <h2>Saga Participant Role</h2>
 * <p>This service does NOT orchestrate it only reacts to commands (events).
 *
 * <h2>Idempotency</h2>
 * <p>Kafka delivers messages at-least-once. The unique constraint on
 * order_id ensures that duplicate events produce no additional side-effects.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class AccountingService {

    /**
     * Repository for consumer accounts.
     */
    private final ConsumerAccountRepository accountRepository;

    /**
     * Repository for payment authorizations.
     */
    private final PaymentAuthorizationRepository authorizationRepository;

    /**
     * Kafka publisher for payment events.
     */
    private final PaymentEventPublisher eventPublisher;

    /**
     * Processes an OrderCreated event: authorizes payment or declines.
     *
     * @param event the inbound OrderCreated event
     */
    @Transactional
    public void processOrderCreated(final OrderCreatedEvent event) {
        log.info("Processing OrderCreated event: orderId={}, "
                + "consumerId={}, amount={}",
                event.getOrderId(), event.getConsumerId(),
                event.getOrderTotal());

        final Optional<PaymentAuthorization> existing =
                authorizationRepository.findByOrderId(event.getOrderId());

        if (existing.isPresent()) {
            log.warn("Duplicate OrderCreated event detected for orderId={}. "
                    + "Replaying existing result without reprocessing.",
                    event.getOrderId());
            replayResult(existing.get(), event);
            return;
        }

        final Optional<ConsumerAccount> accountOpt =
                accountRepository.findById(event.getConsumerId());

        if (accountOpt.isEmpty()) {
            log.error("Consumer account not found for consumerId={}. "
                    + "Declining payment for orderId={}",
                    event.getConsumerId(), event.getOrderId());
            persistAndPublishDecline(event, "CONSUMER_ACCOUNT_NOT_FOUND");
            return;
        }

        final ConsumerAccount account = accountOpt.get();
        final boolean authorized = account.authorize(event.getOrderTotal());

        if (authorized) {
            accountRepository.save(account);

            final PaymentAuthorization authorization =
                    PaymentAuthorization.builder()
                            .orderId(event.getOrderId())
                            .consumerId(event.getConsumerId())
                            .amount(event.getOrderTotal())
                            .status(AuthorizationStatus.AUTHORIZED)
                            .build();
            authorizationRepository.save(authorization);

            log.info("Payment authorized for orderId={}, amount={}",
                    event.getOrderId(), event.getOrderTotal());

            eventPublisher.publishPaymentAuthorized(
                    PaymentAuthorizedEvent.builder()
                            .orderId(event.getOrderId())
                            .consumerId(event.getConsumerId())
                            .authorizedAmount(event.getOrderTotal())
                            .authorizedAt(Instant.now())
                            .build());
        } else {
            log.warn("Payment declined for orderId={} — insufficient funds. "
                    + "Available: {}, Required: {}", event.getOrderId(),
                    account.getAvailableCredit(), event.getOrderTotal());
            persistAndPublishDecline(event, "INSUFFICIENT_FUNDS");
        }
    }

    /**
     * Compensating transaction: reverse a previously authorized payment hold.
     *
     * @param orderId the order whose authorization should be reversed
     */
    @Transactional
    public void reverseAuthorization(final Long orderId) {
        log.info("Reversing payment authorization for orderId={}", orderId);

        final PaymentAuthorization auth =
                authorizationRepository.findByOrderId(orderId)
                .orElseThrow(() -> new IllegalStateException(
                        "No authorization record found for orderId="
                        + orderId));

        if (!AuthorizationStatus.AUTHORIZED.equals(auth.getStatus())) {
            log.warn("Cannot reverse authorization for orderId={} status is {}",
                    orderId, auth.getStatus());
            return;
        }

        final ConsumerAccount account =
                accountRepository.findById(auth.getConsumerId())
                .orElseThrow(() -> new IllegalStateException(
                        "Consumer account missing for consumerId="
                        + auth.getConsumerId()));

        account.releaseAuthorization(auth.getAmount());
        accountRepository.save(account);

        auth.setStatus(AuthorizationStatus.REVERSED);
        authorizationRepository.save(auth);

        log.info("Authorization reversed for orderId={}, amount={} "
                + "returned to consumerId={}",
                orderId, auth.getAmount(), auth.getConsumerId());
    }

    /**
     * Persists a declined authorization and publishes the failure event.
     *
     * @param event  the original order created event
     * @param reason the reason for the decline
     */
    private void persistAndPublishDecline(final OrderCreatedEvent event,
                                          final String reason) {
        final PaymentAuthorization authorization =
                PaymentAuthorization.builder()
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

    /**
     * Replays the result of an existing authorization.
     *
     * @param existing the existing payment authorization
     * @param event    the incoming order created event
     */
    private void replayResult(final PaymentAuthorization existing,
                              final OrderCreatedEvent event) {
        if (existing.isAuthorized()) {
            eventPublisher.publishPaymentAuthorized(
                    PaymentAuthorizedEvent.builder()
                            .orderId(existing.getOrderId())
                            .consumerId(existing.getConsumerId())
                            .authorizedAmount(existing.getAmount())
                            .authorizedAt(existing.getCreatedAt())
                            .build());
        } else {
            eventPublisher.publishPaymentFailed(
                    PaymentFailedEvent.builder()
                            .orderId(existing.getOrderId())
                            .consumerId(existing.getConsumerId())
                            .amount(existing.getAmount())
                            .reason(existing.getDeclineReason())
                            .failedAt(existing.getCreatedAt())
                            .build());
        }
    }
}
