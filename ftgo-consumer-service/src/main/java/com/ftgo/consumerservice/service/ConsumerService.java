package com.ftgo.consumerservice.service;

import com.ftgo.consumerservice.dto.ConsumerResponse;
import com.ftgo.consumerservice.dto.CreateConsumerRequest;
import com.ftgo.consumerservice.entity.Consumer;
import com.ftgo.consumerservice.entity.PersonName;
import com.ftgo.consumerservice.exception.ConsumerNotFoundException;
import com.ftgo.consumerservice.repository.ConsumerRepository;
import org.springframework.stereotype.Service;

@Service
public class ConsumerService {

    private final ConsumerRepository repository;

    public ConsumerService(ConsumerRepository repository) {
        this.repository = repository;
    }

    public ConsumerResponse createConsumer(CreateConsumerRequest request) {

        Consumer consumer = new Consumer(
                new PersonName(
                        request.getFirstName(),
                        request.getLastName()
                )
        );

        Consumer saved = repository.save(consumer);

        return new ConsumerResponse(
                saved.getId(),
                saved.getName().getFirstName(),
                saved.getName().getLastName()
        );
    }

    public ConsumerResponse getConsumer(Long id) {

        Consumer consumer = repository.findById(id)
                .orElseThrow(() -> new ConsumerNotFoundException(id));

        return new ConsumerResponse(
                consumer.getId(),
                consumer.getName().getFirstName(),
                consumer.getName().getLastName()
        );
    }
}