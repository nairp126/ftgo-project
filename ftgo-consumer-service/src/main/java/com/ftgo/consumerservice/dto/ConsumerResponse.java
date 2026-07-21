package com.ftgo.consumerservice.dto;

public class ConsumerResponse {

    private Long id;
    private String firstName;
    private String lastName;

    public ConsumerResponse(Long id, String firstName, String lastName) {
        this.id = id;
        this.firstName = firstName;
        this.lastName = lastName;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }
}