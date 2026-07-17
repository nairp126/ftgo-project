package com.ftgo.accounting.repository;

import com.ftgo.accounting.domain.PaymentAuthorization;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface PaymentAuthorizationRepository extends JpaRepository<PaymentAuthorization, Long> {

    /**
     * Idempotency lookup: find an existing authorization record for a given orderId.
     * If present, the event is a duplicate and should not be reprocessed.
     */
    Optional<PaymentAuthorization> findByOrderId(Long orderId);
}
