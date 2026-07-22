package com.ftgo.accounting.repository;

import com.ftgo.accounting.domain.ConsumerAccount;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

/**
 * Spring Data JPA repository for the {@link ConsumerAccount} entity.
 */
@Repository
public interface ConsumerAccountRepository
        extends JpaRepository<ConsumerAccount, Long> {
}
