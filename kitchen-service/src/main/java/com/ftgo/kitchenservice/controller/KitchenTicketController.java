package com.ftgo.kitchenservice.controller;

import com.ftgo.kitchenservice.dto.KitchenTicketCreateRequest;
import com.ftgo.kitchenservice.dto.KitchenTicketResponse;
import com.ftgo.kitchenservice.entity.KitchenTicketStatus;
import com.ftgo.kitchenservice.service.KitchenTicketService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/kitchen/tickets")
@RequiredArgsConstructor
public class KitchenTicketController {

    private final KitchenTicketService kitchenTicketService;

    @PostMapping
    public ResponseEntity<KitchenTicketResponse> create(@Valid @RequestBody KitchenTicketCreateRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(kitchenTicketService.create(request));
    }

    @GetMapping
    public ResponseEntity<List<KitchenTicketResponse>> findAll() {
        return ResponseEntity.ok(kitchenTicketService.findAll());
    }

    @GetMapping("/{ticketId}")
    public ResponseEntity<KitchenTicketResponse> findById(@PathVariable UUID ticketId) {
        return ResponseEntity.ok(kitchenTicketService.findById(ticketId));
    }

    @GetMapping("/restaurant/{restaurantId}")
    public ResponseEntity<List<KitchenTicketResponse>> findByRestaurant(@PathVariable UUID restaurantId) {
        return ResponseEntity.ok(kitchenTicketService.findByRestaurant(restaurantId));
    }

    @PatchMapping("/{ticketId}/accept")
    public ResponseEntity<KitchenTicketResponse> accept(@PathVariable UUID ticketId) {
        return ResponseEntity.ok(kitchenTicketService.updateStatus(ticketId, KitchenTicketStatus.ACCEPTED));
    }

    @PatchMapping("/{ticketId}/preparing")
    public ResponseEntity<KitchenTicketResponse> preparing(@PathVariable UUID ticketId) {
        return ResponseEntity.ok(kitchenTicketService.updateStatus(ticketId, KitchenTicketStatus.PREPARING));
    }

    @PatchMapping("/{ticketId}/ready")
    public ResponseEntity<KitchenTicketResponse> ready(@PathVariable UUID ticketId) {
        return ResponseEntity.ok(kitchenTicketService.updateStatus(ticketId, KitchenTicketStatus.READY));
    }

    @PatchMapping("/{ticketId}/cancel")
    public ResponseEntity<KitchenTicketResponse> cancel(@PathVariable UUID ticketId) {
        return ResponseEntity.ok(kitchenTicketService.updateStatus(ticketId, KitchenTicketStatus.CANCELLED));
    }

    @DeleteMapping("/{ticketId}")
    public ResponseEntity<Void> delete(@PathVariable UUID ticketId) {
        kitchenTicketService.delete(ticketId);
        return ResponseEntity.noContent().build();
    }
}
