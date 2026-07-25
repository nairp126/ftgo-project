package com.ftgo.orderhistoryservice.service;

import com.ftgo.orderhistoryservice.entity.OrderHistory;
import com.ftgo.orderhistoryservice.kafka.dto.accounting.PaymentAuthorizedEvent;
import com.ftgo.orderhistoryservice.kafka.dto.accounting.PaymentFailedEvent;
import com.ftgo.orderhistoryservice.kafka.dto.kitchen.TicketCreatedEvent;
import com.ftgo.orderhistoryservice.kafka.dto.kitchen.TicketRejectedEvent;
import com.ftgo.orderhistoryservice.repository.OrderHistoryRepository;
import jakarta.transaction.Transactional;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class OrderHistoryService {

    private final OrderHistoryRepository repository;

    public OrderHistoryService(OrderHistoryRepository repository) {
        this.repository = repository;
    }

    public List<OrderHistory> getAllOrders() {
        return repository.findAll();
    }

    public List<OrderHistory> getOrdersByConsumerId(Long consumerId) {
        return repository.findByConsumerId(consumerId);
    }

    public OrderHistory getOrder(Long id) {
        return repository.findById(id).orElse(null);
    }

    public OrderHistory saveOrder(OrderHistory orderHistory) {
        return repository.save(orderHistory);
    }

    public void deleteOrder(Long id) {
        repository.deleteById(id);
    }

    @Transactional
    public void handlePaymentAuthorized(PaymentAuthorizedEvent event) {

        OrderHistory orderHistory = repository.findByOrderId(event.getOrderId())
                .orElseThrow(() ->
                        new RuntimeException("Order not found: " + event.getOrderId()));

        orderHistory.setOrderStatus("PAYMENT_AUTHORIZED");

        repository.save(orderHistory);
    }

    @Transactional
    public void handlePaymentFailed(PaymentFailedEvent event) {

        OrderHistory orderHistory = repository.findByOrderId(event.getOrderId())
                .orElseThrow(() ->
                        new RuntimeException("Order not found: " + event.getOrderId()));

        orderHistory.setOrderStatus("PAYMENT_FAILED");

        repository.save(orderHistory);
    }

    @Transactional
    public void handleTicketCreated(TicketCreatedEvent event) {

        OrderHistory orderHistory = repository.findByOrderId(event.orderId())
                .orElseThrow(() ->
                        new RuntimeException("Order not found: " + event.orderId()));

        orderHistory.setOrderStatus("TICKET_CREATED");

        repository.save(orderHistory);
    }

    @Transactional
    public void handleTicketRejected(TicketRejectedEvent event) {

        OrderHistory orderHistory = repository.findByOrderId(event.orderId())
                .orElseThrow(() ->
                        new RuntimeException("Order not found: " + event.orderId()));

        orderHistory.setOrderStatus("TICKET_REJECTED");

        repository.save(orderHistory);
    }
}