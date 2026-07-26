package com.ftgo.kitchenservice.dto;

import com.ftgo.kitchenservice.entity.KitchenTicketStatus;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record KitchenTicketResponse(
        UUID id,
        UUID restaurantId,
        UUID orderId,
        KitchenTicketStatus status,
        String rejectionReason,
        List<KitchenTicketItemResponse> items,
        Instant createdAt,
        Instant updatedAt,
        Instant acceptedAt,
        Instant readyAt,
        Instant cancelledAt
) {
}
