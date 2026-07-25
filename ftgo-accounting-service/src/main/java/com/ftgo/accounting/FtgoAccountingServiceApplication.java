package com.ftgo.accounting;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Entry point for the FTGO Accounting Service.
 *
 * <p>Responsibilities:
 * <ul>
 *   <li>Manages consumer accounts and payment authorization state.</li>
 *   <li>Participates in the create-order Saga as a participant.</li>
 *   <li>Consumes {@code order.created} Kafka events and publishes
 *       {@code payment.authorized} or {@code payment.failed} in response.</li>
 * </ul>
 *
 * <p>PCI Compliance note: this service is the <em>only</em> service
 * that touches cardholder-adjacent data. Keeping it isolated minimises
 */
@SpringBootApplication
public final class FtgoAccountingServiceApplication {

    /**
     * Private constructor to prevent instantiation of utility class.
     */
    private FtgoAccountingServiceApplication() {
        // Utility class
    }

    /**
     * Main method to start the Spring Boot application.
     *
     * @param args the command line arguments
     */
    public static void main(final String[] args) {
        SpringApplication.run(FtgoAccountingServiceApplication.class, args);
    }
}
