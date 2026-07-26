package com.ftgo.kitchenservice.mapper;

import com.ftgo.kitchenservice.dto.KitchenTicketItemResponse;
import com.ftgo.kitchenservice.dto.KitchenTicketResponse;
import com.ftgo.kitchenservice.entity.KitchenTicket;
import com.ftgo.kitchenservice.entity.KitchenTicketItem;
import org.springframework.stereotype.Component;

@Component
public class KitchenTicketMapper {

    public KitchenTicketResponse toResponse(KitchenTicket ticket) {
        return new KitchenTicketResponse(
                ticket.getId(),
                ticket.getRestaurantId(),
                ticket.getOrderId(),
                ticket.getStatus(),
                ticket.getRejectionReason(),
                ticket.getItems().stream().map(this::toItemResponse).toList(),
                ticket.getCreatedAt(),
                ticket.getUpdatedAt(),
                ticket.getAcceptedAt(),
                ticket.getReadyAt(),
                ticket.getCancelledAt()
        );
    }

    private KitchenTicketItemResponse toItemResponse(KitchenTicketItem item) {
        return new KitchenTicketItemResponse(
                item.getId(),
                item.getMenuItemId(),
                item.getName(),
                item.getQuantity(),
                item.getSpecialInstructions()
        );
    }
}
