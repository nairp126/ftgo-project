## Accounting Service Data Ownership

**Owned Data:**
- `Account`: Stores customer billing details, available balances, and credit limits.
- `Payment`: Stores transaction records, timestamps, and authorization states.

**Shared Data Challenges & Solutions:**
- **Challenge:** The Order Service needs to know if an order is financially authorized before confirming it to the restaurant. However, the Order Service does not (and should not) have access to customer credit card details or balances.
- **Solution:** We use the Saga pattern with asynchronous messaging. The Order Service creates an order in a `PENDING` state and emits an `OrderCreatedEvent`. The Accounting Service listens for this event, securely processes the payment against its isolated `Account` database, and emits an `AccountAuthorizedEvent`. The Order Service then updates the order to `APPROVED`. This ensures strict microservice data isolation while keeping the system eventually consistent.
