package com.ftgo.accounting.repository;

import com.ftgo.accounting.domain.PaymentAuthorization;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

/**
 * Spring Data JPA repository for the {@link PaymentAuthorization} entity.
 */
@Repository
public interface PaymentAuthorizationRepository
        extends JpaRepository<PaymentAuthorization, Long> {

    /**
     * Idempotency lookup: find an existing authorization record for an orderId.
     * If present, the event is a duplicate and should not be reprocessed.
     *
     * @param orderId the global order identifier
     * @return an optional payment authorization
     */
    Optional<PaymentAuthorization> findByOrderId(Long orderId);
}
