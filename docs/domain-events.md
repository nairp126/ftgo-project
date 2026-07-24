## Accounting Service Domain Events

The Accounting Service publishes and subscribes to the following domain events as part of the system's sagas:

**Subscribes To:**
- `OrderCreatedEvent` (from Order Service): Triggers the Accounting Service to verify the customer's credit limit and authorize the payment.
- `OrderCancelledEvent` (from Order Service): Triggers the Accounting Service to reverse the authorization and refund the customer.

**Publishes:**
- `AccountAuthorizedEvent`: Published when a customer's credit card is successfully authorized.
- `AccountAuthorizationFailedEvent`: Published when a customer's credit card is declined due to insufficient funds.
