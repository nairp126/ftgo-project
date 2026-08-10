package com.ftgo.consumerservice.controller;

import com.ftgo.consumerservice.dto.ConsumerResponse;
import com.ftgo.consumerservice.dto.CreateConsumerRequest;
import com.ftgo.consumerservice.service.ConsumerService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/consumers")
public class ConsumerController {

    private final ConsumerService consumerService;

    public ConsumerController(ConsumerService consumerService) {
        this.consumerService = consumerService;
    }

    @PostMapping
    public ConsumerResponse createConsumer(
            @Valid @RequestBody CreateConsumerRequest request) {

        return consumerService.createConsumer(request);
    }

    @GetMapping("/{id}")
    public ConsumerResponse getConsumer(@PathVariable Long id) {
        return consumerService.getConsumer(id);
    }
}