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
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.*;

/**
 * Unit tests for {@link AccountingService}.
 *
 * <p>Covers three critical scenarios required by the spec:
 * <ol>
 *   <li>Successful payment authorization (sufficient funds)</li>
 *   <li>Failed payment authorization (insufficient funds)</li>
 *   <li>Idempotent event handling (duplicate {@code OrderCreated} — no double-charge)</li>
 * </ol>
 *
 * <p>Uses Mockito to isolate the service from real Kafka/database dependencies.
 * No Spring context is loaded — these are pure unit tests and run in milliseconds.
 */
@ExtendWith(MockitoExtension.class)
@DisplayName("AccountingService Unit Tests")
class AccountingServiceTest {

    @Mock
    private ConsumerAccountRepository accountRepository;

    @Mock
    private PaymentAuthorizationRepository authorizationRepository;

    @Mock
    private PaymentEventPublisher eventPublisher;

    @InjectMocks
    private AccountingService accountingService;

    @Captor
    private ArgumentCaptor<PaymentAuthorization> authCaptor;

    @Captor
    private ArgumentCaptor<PaymentAuthorizedEvent> authorizedEventCaptor;

    @Captor
    private ArgumentCaptor<PaymentFailedEvent> failedEventCaptor;

    // ── Test fixtures ─────────────────────────────────────────────────────────

    private static final Long ORDER_ID = 1001L;
    private static final Long CONSUMER_ID = 42L;
    private static final BigDecimal ORDER_TOTAL = new BigDecimal("49.99");

    private ConsumerAccount consumerAccount;
    private OrderCreatedEvent orderCreatedEvent;

    @BeforeEach
    void setUp() {
        consumerAccount = ConsumerAccount.builder()
                .consumerId(CONSUMER_ID)
                .availableCredit(new BigDecimal("500.00"))
                .createdAt(Instant.now())
                .updatedAt(Instant.now())
                .build();

        orderCreatedEvent = OrderCreatedEvent.builder()
                .orderId(ORDER_ID)
                .consumerId(CONSUMER_ID)
                .orderTotal(ORDER_TOTAL)
                .build();
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Scenario 1: Successful Authorization
    // ═════════════════════════════════════════════════════════════════════════

    @Nested
    @DisplayName("Scenario 1: Successful Payment Authorization")
    class SuccessfulAuthorization {

        @BeforeEach
        void setUpMocks() {
            // No existing record → fresh event
            when(authorizationRepository.findByOrderId(ORDER_ID)).thenReturn(Optional.empty());
            // Consumer has sufficient funds
            when(accountRepository.findById(CONSUMER_ID)).thenReturn(Optional.of(consumerAccount));
            when(authorizationRepository.save(any())).thenAnswer(i -> i.getArgument(0));
            when(accountRepository.save(any())).thenAnswer(i -> i.getArgument(0));
        }

        @Test
        @DisplayName("Should place a credit hold and publish PaymentAuthorized event")
        void shouldAuthorizePaymentAndPublishEvent() {
            // Act
            accountingService.processOrderCreated(orderCreatedEvent);

            // Assert: authorization record saved with AUTHORIZED status
            verify(authorizationRepository).save(authCaptor.capture());
            PaymentAuthorization savedAuth = authCaptor.getValue();
            assertThat(savedAuth.getOrderId()).isEqualTo(ORDER_ID);
            assertThat(savedAuth.getConsumerId()).isEqualTo(CONSUMER_ID);
            assertThat(savedAuth.getAmount()).isEqualByComparingTo(ORDER_TOTAL);
            assertThat(savedAuth.getStatus()).isEqualTo(AuthorizationStatus.AUTHORIZED);

            // Assert: consumer account credit was reduced
            verify(accountRepository).save(consumerAccount);
            assertThat(consumerAccount.getAvailableCredit())
                    .isEqualByComparingTo(new BigDecimal("450.01")); // 500.00 - 49.99

            // Assert: PaymentAuthorized event published
            verify(eventPublisher).publishPaymentAuthorized(authorizedEventCaptor.capture());
            PaymentAuthorizedEvent publishedEvent = authorizedEventCaptor.getValue();
            assertThat(publishedEvent.getOrderId()).isEqualTo(ORDER_ID);
            assertThat(publishedEvent.getConsumerId()).isEqualTo(CONSUMER_ID);
            assertThat(publishedEvent.getAuthorizedAmount()).isEqualByComparingTo(ORDER_TOTAL);
            assertThat(publishedEvent.getAuthorizedAt()).isNotNull();

            // Assert: PaymentFailed was NOT published
            verify(eventPublisher, never()).publishPaymentFailed(any());
        }
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Scenario 2: Failed Authorization (Insufficient Funds)
    // ═════════════════════════════════════════════════════════════════════════

    @Nested
    @DisplayName("Scenario 2: Failed Payment Authorization — Insufficient Funds")
    class FailedAuthorization {

        @BeforeEach
        void setUpMocks() {
            // Consumer has LESS than order total
            ConsumerAccount poorAccount = ConsumerAccount.builder()
                    .consumerId(CONSUMER_ID)
                    .availableCredit(new BigDecimal("10.00"))  // only $10, needs $49.99
                    .createdAt(Instant.now())
                    .updatedAt(Instant.now())
                    .build();

            when(authorizationRepository.findByOrderId(ORDER_ID)).thenReturn(Optional.empty());
            when(accountRepository.findById(CONSUMER_ID)).thenReturn(Optional.of(poorAccount));
            when(authorizationRepository.save(any())).thenAnswer(i -> i.getArgument(0));
        }

        @Test
        @DisplayName("Should persist a DECLINED record and publish PaymentFailed event")
        void shouldDeclinePaymentAndPublishFailureEvent() {
            // Act
            accountingService.processOrderCreated(orderCreatedEvent);

            // Assert: authorization record saved with DECLINED status
            verify(authorizationRepository).save(authCaptor.capture());
            PaymentAuthorization savedAuth = authCaptor.getValue();
            assertThat(savedAuth.getStatus()).isEqualTo(AuthorizationStatus.DECLINED);
            assertThat(savedAuth.getDeclineReason()).isEqualTo("INSUFFICIENT_FUNDS");

            // Assert: PaymentFailed event published
            verify(eventPublisher).publishPaymentFailed(failedEventCaptor.capture());
            PaymentFailedEvent failedEvent = failedEventCaptor.getValue();
            assertThat(failedEvent.getOrderId()).isEqualTo(ORDER_ID);
            assertThat(failedEvent.getReason()).isEqualTo("INSUFFICIENT_FUNDS");
            assertThat(failedEvent.getAmount()).isEqualByComparingTo(ORDER_TOTAL);

            // Assert: PaymentAuthorized was NOT published
            verify(eventPublisher, never()).publishPaymentAuthorized(any());

            // Assert: account balance unchanged (no deduction on decline)
            verify(accountRepository, never()).save(any());
        }

        @Test
        @DisplayName("Should decline when consumer account does not exist")
        void shouldDeclineWhenAccountNotFound() {
            when(accountRepository.findById(CONSUMER_ID)).thenReturn(Optional.empty());

            accountingService.processOrderCreated(orderCreatedEvent);

            verify(authorizationRepository).save(authCaptor.capture());
            assertThat(authCaptor.getValue().getStatus()).isEqualTo(AuthorizationStatus.DECLINED);
            assertThat(authCaptor.getValue().getDeclineReason()).isEqualTo("CONSUMER_ACCOUNT_NOT_FOUND");

            verify(eventPublisher).publishPaymentFailed(any());
            verify(eventPublisher, never()).publishPaymentAuthorized(any());
        }
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Scenario 3: Idempotency — Duplicate OrderCreated Event
    // ═════════════════════════════════════════════════════════════════════════

    @Nested
    @DisplayName("Scenario 3: Idempotent Event Handling (Duplicate OrderCreated)")
    class IdempotentEventHandling {

        /**
         * This test verifies the PRIMARY idempotency guarantee:
         *
         * If Kafka delivers the same OrderCreated event more than once (at-least-once delivery),
         * the service must NOT:
         *   - Make a second authorization attempt
         *   - Deduct the consumer's credit a second time (i.e., no double-charge)
         *   - Create a second PaymentAuthorization record
         *
         * Instead, it should replay the existing outcome.
         */
        @Test
        @DisplayName("Should NOT re-authorize if OrderCreated was already processed (no double-charge)")
        void shouldNotDoubleChargeOnDuplicateEvent() {
            // Arrange: a record already exists for this orderId (first delivery was processed)
            PaymentAuthorization existingAuth = PaymentAuthorization.builder()
                    .id(1L)
                    .orderId(ORDER_ID)
                    .consumerId(CONSUMER_ID)
                    .amount(ORDER_TOTAL)
                    .status(AuthorizationStatus.AUTHORIZED)
                    .createdAt(Instant.now())
                    .updatedAt(Instant.now())
                    .build();

            when(authorizationRepository.findByOrderId(ORDER_ID)).thenReturn(Optional.of(existingAuth));

            // Act: second delivery of the same event
            accountingService.processOrderCreated(orderCreatedEvent);

            // Assert: NO new authorization record was saved
            verify(authorizationRepository, never()).save(any());

            // Assert: consumer account was NOT modified again
            verify(accountRepository, never()).findById(anyLong());
            verify(accountRepository, never()).save(any());

            // Assert: existing result (PaymentAuthorized) was replayed
            verify(eventPublisher).publishPaymentAuthorized(authorizedEventCaptor.capture());
            PaymentAuthorizedEvent replayed = authorizedEventCaptor.getValue();
            assertThat(replayed.getOrderId()).isEqualTo(ORDER_ID);

            // Assert: failure event was NOT published
            verify(eventPublisher, never()).publishPaymentFailed(any());
        }

        @Test
        @DisplayName("Should replay PaymentFailed for previously declined duplicate event")
        void shouldReplayDeclineForDuplicateDeclinedEvent() {
            // Arrange: a DECLINED record already exists
            PaymentAuthorization declinedAuth = PaymentAuthorization.builder()
                    .id(2L)
                    .orderId(ORDER_ID)
                    .consumerId(CONSUMER_ID)
                    .amount(ORDER_TOTAL)
                    .status(AuthorizationStatus.DECLINED)
                    .declineReason("INSUFFICIENT_FUNDS")
                    .createdAt(Instant.now())
                    .updatedAt(Instant.now())
                    .build();

            when(authorizationRepository.findByOrderId(ORDER_ID)).thenReturn(Optional.of(declinedAuth));

            // Act: duplicate delivery
            accountingService.processOrderCreated(orderCreatedEvent);

            // Assert: no new records, existing failure replayed
            verify(authorizationRepository, never()).save(any());
            verify(accountRepository, never()).findById(anyLong());
            verify(eventPublisher).publishPaymentFailed(failedEventCaptor.capture());
            assertThat(failedEventCaptor.getValue().getReason()).isEqualTo("INSUFFICIENT_FUNDS");
            verify(eventPublisher, never()).publishPaymentAuthorized(any());
        }
    }
}
