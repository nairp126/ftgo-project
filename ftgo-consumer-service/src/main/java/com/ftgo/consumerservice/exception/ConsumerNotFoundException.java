package com.ftgo.consumerservice.exception;

public class ConsumerNotFoundException extends RuntimeException {

    public ConsumerNotFoundException(Long id) {
        super("Consumer with id " + id + " not found");
    }
}