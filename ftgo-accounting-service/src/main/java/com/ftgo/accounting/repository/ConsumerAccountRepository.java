package com.ftgo.accounting.repository;

import com.ftgo.accounting.domain.ConsumerAccount;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface ConsumerAccountRepository extends JpaRepository<ConsumerAccount, Long> {
    // findById(consumerId) inherited from JpaRepository
}
