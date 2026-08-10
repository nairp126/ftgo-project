package com.ftgo.kitchenservice.service;

import com.ftgo.kitchenservice.dto.KitchenTicketCreateRequest;
import com.ftgo.kitchenservice.dto.KitchenTicketItemRequest;
import com.ftgo.kitchenservice.dto.KitchenTicketResponse;
import com.ftgo.kitchenservice.entity.KitchenMenuItem;
import com.ftgo.kitchenservice.entity.KitchenTicket;
import com.ftgo.kitchenservice.entity.KitchenTicketItem;
import com.ftgo.kitchenservice.entity.KitchenTicketStatus;
import com.ftgo.kitchenservice.exception.BusinessRuleException;
import com.ftgo.kitchenservice.exception.ResourceNotFoundException;
import com.ftgo.kitchenservice.kafka.OrderCreatedEvent;
import com.ftgo.kitchenservice.kafka.TicketEventProducer;
import com.ftgo.kitchenservice.mapper.KitchenTicketMapper;
import com.ftgo.kitchenservice.repository.KitchenMenuItemRepository;
import com.ftgo.kitchenservice.repository.KitchenTicketRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class KitchenTicketService {

    private final KitchenTicketRepository kitchenTicketRepository;
    private final KitchenMenuItemRepository kitchenMenuItemRepository;
    private final KitchenTicketMapper kitchenTicketMapper;
    private final TicketEventProducer ticketEventProducer;

    @Transactional
    public KitchenTicketResponse create(KitchenTicketCreateRequest request) {
        if (kitchenTicketRepository.existsByOrderId(request.orderId())) {
            throw new BusinessRuleException("Kitchen ticket already exists for order: " + request.orderId());
        }

        KitchenTicket ticket = buildTicketOrThrow(request);
        KitchenTicket savedTicket = kitchenTicketRepository.save(ticket);
        publishTicketCreatedAfterCommit(savedTicket);
        return kitchenTicketMapper.toResponse(savedTicket);
    }

    @Transactional
    public void handleOrderCreated(OrderCreatedEvent event) {
        if (kitchenTicketRepository.existsByOrderId(event.orderId())) {
            return;
        }

        KitchenTicketCreateRequest request = new KitchenTicketCreateRequest(
                event.restaurantId(),
                event.orderId(),
                event.items().stream()
                        .map(item -> new KitchenTicketItemRequest(
                                item.menuItemId(),
                                item.quantity(),
                                item.specialInstructions()
                        ))
                        .toList()
        );

        try {
            KitchenTicket ticket = buildTicketOrThrow(request);
            KitchenTicket savedTicket = kitchenTicketRepository.save(ticket);
            publishTicketCreatedAfterCommit(savedTicket);
        } catch (BusinessRuleException exception) {
            publishTicketRejectedAfterCommit(event.orderId(), event.restaurantId(), exception.getMessage());
        }
    }

    @Transactional(readOnly = true)
    public List<KitchenTicketResponse> findAll() {
        return kitchenTicketRepository.findAll()
                .stream()
                .map(kitchenTicketMapper::toResponse)
                .toList();
    }

    @Transactional(readOnly = true)
    public KitchenTicketResponse findById(UUID ticketId) {
        return kitchenTicketMapper.toResponse(getTicketOrThrow(ticketId));
    }

    @Transactional(readOnly = true)
    public List<KitchenTicketResponse> findByRestaurant(UUID restaurantId) {
        return kitchenTicketRepository.findByRestaurantIdOrderByCreatedAtDesc(restaurantId)
                .stream()
                .map(kitchenTicketMapper::toResponse)
                .toList();
    }

    @Transactional
    public KitchenTicketResponse updateStatus(UUID ticketId, KitchenTicketStatus status) {
        KitchenTicket ticket = getTicketOrThrow(ticketId);
        ticket.setStatus(status);

        Instant now = Instant.now();
        if (status == KitchenTicketStatus.ACCEPTED) {
            ticket.setAcceptedAt(now);
        } else if (status == KitchenTicketStatus.READY) {
            ticket.setReadyAt(now);
        } else if (status == KitchenTicketStatus.CANCELLED) {
            ticket.setCancelledAt(now);
        }

        return kitchenTicketMapper.toResponse(kitchenTicketRepository.save(ticket));
    }

    @Transactional
    public void delete(UUID ticketId) {
        KitchenTicket ticket = getTicketOrThrow(ticketId);
        kitchenTicketRepository.delete(ticket);
    }

    private KitchenTicket buildTicketOrThrow(KitchenTicketCreateRequest request) {
        Map<UUID, KitchenMenuItem> menuItemsById = kitchenMenuItemRepository.findAllById(
                        request.items().stream().map(KitchenTicketItemRequest::menuItemId).toList()
                )
                .stream()
                .collect(Collectors.toMap(KitchenMenuItem::getId, Function.identity()));

        KitchenTicket ticket = KitchenTicket.builder()
                .restaurantId(request.restaurantId())
                .orderId(request.orderId())
                .status(KitchenTicketStatus.CREATED)
                .build();

        for (KitchenTicketItemRequest itemRequest : request.items()) {
            KitchenMenuItem menuItem = menuItemsById.get(itemRequest.menuItemId());
            if (menuItem == null) {
                throw new BusinessRuleException("Menu item is not replicated in kitchen: " + itemRequest.menuItemId());
            }
            if (!request.restaurantId().equals(menuItem.getRestaurantId())) {
                throw new BusinessRuleException("Menu item does not belong to restaurant: " + itemRequest.menuItemId());
            }
            if (!menuItem.isAvailable()) {
                throw new BusinessRuleException("Menu item is unavailable: " + itemRequest.menuItemId());
            }

            ticket.addItem(KitchenTicketItem.builder()
                    .menuItemId(menuItem.getId())
                    .name(menuItem.getName())
                    .quantity(itemRequest.quantity())
                    .specialInstructions(itemRequest.specialInstructions())
                    .build());
        }

        return ticket;
    }

    private KitchenTicket getTicketOrThrow(UUID ticketId) {
        return kitchenTicketRepository.findById(ticketId)
                .orElseThrow(() -> new ResourceNotFoundException("Kitchen ticket not found: " + ticketId));
    }

    private void publishTicketCreatedAfterCommit(KitchenTicket ticket) {
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                ticketEventProducer.publishTicketCreated(ticket);
            }
        });
    }

    private void publishTicketRejectedAfterCommit(UUID orderId, UUID restaurantId, String reason) {
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                ticketEventProducer.publishTicketRejected(orderId, restaurantId, reason);
            }
        });
    }
}
