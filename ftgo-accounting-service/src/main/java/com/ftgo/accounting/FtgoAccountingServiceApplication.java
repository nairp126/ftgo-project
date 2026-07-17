package com.ftgo.accounting;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Entry point for the FTGO Accounting Service.
 *
 * <p>Responsibilities:
 * <ul>
 *   <li>Manages consumer accounts and payment authorization state (database-per-service).</li>
 *   <li>Participates in the create-order Saga as a <em>participant</em> (not orchestrator).</li>
 *   <li>Consumes {@code order.created} Kafka events and publishes
 *       {@code payment.authorized} or {@code payment.failed} in response.</li>
 * </ul>
 *
 * <p>PCI Compliance note: this service is the <em>only</em> service that touches
 * cardholder-adjacent data.  Keeping it isolated minimises the PCI DSS audit surface.
 */
@SpringBootApplication
public class FtgoAccountingServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(FtgoAccountingServiceApplication.class, args);
    }
}
