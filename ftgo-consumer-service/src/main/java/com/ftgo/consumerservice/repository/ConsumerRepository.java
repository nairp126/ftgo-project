package com.ftgo.consumerservice.repository;

import com.ftgo.consumerservice.entity.Consumer;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ConsumerRepository extends JpaRepository<Consumer, Long> {

}