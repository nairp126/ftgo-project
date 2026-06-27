# Contributing Guide

> This document defines how all five team members work together on this
> repository. Read it once. Follow it always. It prevents merge conflicts,
> lost work, and confusion about who owns what.

---

## Table of Contents

- [Branch Strategy](#branch-strategy)
- [Commit Conventions](#commit-conventions)
- [Pull Request Rules](#pull-request-rules)
- [Who Owns What](#who-owns-what)
- [Roles and Responsibilities](#roles-and-responsibilities)
- [Weekly Workflow](#weekly-workflow)
- [Documents Each Person Maintains](#documents-each-person-maintains)
- [Code Review Expectations](#code-review-expectations)
- [What To Do When Things Break](#what-to-do-when-things-break)

---

## Branch Strategy

```
main          ← protected. Production-ready only. Merge via PR from dev.
dev           ← integration branch. Merge your feature branch here first.
feat/gateway          ← Person 5
feat/order-service    ← Person 1
feat/kitchen          ← Person 2
feat/accounting       ← Person 3
feat/consumer         ← Person 4
```

### Rules

1. **Never push directly to `main`.** Ever. Not even a small fix.
2. **Never push directly to `dev`.** Always PR from your feature branch.
3. Your feature branch is yours. Push to it freely — no approval needed.
4. To merge into `dev`: open a PR, get 1 approval from any team member.
5. To merge `dev` into `main`: Person 5 does this at the end of each week
   after confirming nothing is broken.
6. If your branch is behind `dev`, rebase — do not merge `dev` into your
   branch (keeps history clean).

```bash
# Correct way to stay up to date with dev
git fetch origin
git rebase origin/dev

# Wrong way (creates noisy merge commits)
git merge origin/dev   ← do not do this
```

---

## Commit Conventions

Use this format for every commit. It makes the git log readable and
makes your CI/CD path filters work correctly.

```
<type>(<scope>): <short description>

Types:
  feat      New feature or capability
  fix       Bug fix
  chore     Build, config, or tooling change (no production code)
  docs      Documentation only
  test      Adding or fixing tests
  refactor  Code change that is not a feat or fix
  ci        GitHub Actions workflow change

Scopes (use your service name):
  order-service
  kitchen-service
  restaurant-service
  accounting-service
  consumer-service
  order-history-service
  gateway
  k8s
  docs
```

### Examples

```bash
# Good commits
git commit -m "feat(order-service): implement create order saga orchestration"
git commit -m "fix(gateway): scope budget check to /v1/ routes only"
git commit -m "chore(k8s): add liveness probe to order service deployment"
git commit -m "docs(adr): complete ADR-002 order service boundary decisions"
git commit -m "ci(order-service): add GitHub Actions build and push pipeline"

# Bad commits (do not do this)
git commit -m "fix stuff"
git commit -m "WIP"
git commit -m "final version"
git commit -m "aaaaaa"
```

---

## Pull Request Rules

### Before opening a PR

- [ ] Your code builds locally (`./gradlew build` or `docker build`)
- [ ] Your service starts without errors (`docker compose up <service>`)
- [ ] You have written or updated your ADR if your PR changes
      an architectural decision
- [ ] Your PR only touches files in your service folder and your
      `k8s/<service>/` folder
      (Exception: `docs/`, `docker-compose.yml` — discuss first)

### PR title format

```
[Person Name] feat(order-service): implement saga orchestration
```

### PR description template

Copy this into every PR description:

```markdown
## What this PR does
<!-- 1-3 sentences -->

## Service affected
<!-- e.g. Order Service -->

## How to test locally
<!-- Steps to verify this works -->

## ADR updated?
<!-- Yes — link to ADR / No — no architectural decision was changed -->

## Checklist
- [ ] Builds locally
- [ ] No hardcoded secrets or credentials
- [ ] K8s manifests updated if service config changed
- [ ] ADR updated if an architectural decision changed
```

### Review turnaround

- PR reviews must be done within **24 hours** of being requested.
- If you are blocked on a PR review for more than 24 hours, message
  the group chat directly.

---

## Who Owns What

Ownership means: you are the decision-maker for your files. Others
can suggest changes but you have final say. You are also responsible
for keeping your files working.

| Person | Files They Own | No One Else Touches Without Asking |
|--------|---------------|-----------------------------------|
| Person 1 | `ftgo-order-service/**` `k8s/order-service/**` `.github/workflows/order-service.yml` `docs/adr/ADR-002-order-service.md` | Yes |
| Person 2 | `ftgo-kitchen-service/**` `ftgo-restaurant-service/**` `k8s/kitchen-service/**` `k8s/restaurant-service/**` `.github/workflows/kitchen-service.yml` `.github/workflows/restaurant-service.yml` `docs/adr/ADR-003-kitchen-restaurant.md` | Yes |
| Person 3 | `ftgo-accounting-service/**` `k8s/accounting-service/**` `.github/workflows/accounting-service.yml` `docs/adr/ADR-004-accounting.md` | Yes |
| Person 4 | `ftgo-consumer-service/**` `ftgo-order-history-service/**` `k8s/consumer-service/**` `k8s/order-history-service/**` `.github/workflows/consumer-service.yml` `.github/workflows/order-history-service.yml` `docs/adr/ADR-005-consumer-cqrs.md` | Yes |
| Person 5 | `universal-ai-gateway/**` `k8s/gateway/**` `k8s/ingress/**` `.github/workflows/gateway.yml` `docs/adr/ADR-001-api-gateway.md` `docs/runbook.md` | Yes |
| All | `docker-compose.yml` `README.md` `docs/adr/ADR-000-master.md` `docs/architecture-diagram.png` `k8s/kafka/**` | Discuss before changing |

---

## Roles and Responsibilities

### Person 1 — Order Service Lead

**You own the most complex service. The Saga pattern lives here.**

Technical responsibilities:
- Implement the create-order Saga orchestration
- Own the `orders` database schema — no other service writes to it
- Publish `OrderCreated`, `OrderCancelled` events to Kafka
- Consume `TicketCreated` (from Kitchen), `PaymentAuthorized` (from
  Accounting) events from Kafka
- Write `k8s/order-service/deployment.yaml`, `service.yaml`,
  `configmap.yaml`
- Write `.github/workflows/order-service.yml` CI/CD pipeline

Documentation responsibilities:
- `docs/adr/ADR-002-order-service.md` — explain the Saga boundary
  decisions, why Order Service is the orchestrator, how rollback works
- Lead the `docs/domain-events.md` document (you have the most events)

Things you must be able to explain in a viva:
- What is the Saga pattern and why do we need it?
- What happens if Kitchen Service rejects the order ticket?
- What happens if Accounting Service fails to authorize payment?
- Why does Order Service not call Kitchen Service via HTTP directly?

---

### Person 2 — Kitchen & Restaurant Service Lead

**You own two services. The interesting problem here is shared data
without a shared database.**

Technical responsibilities:
- Kitchen Service: manage kitchen tickets (the kitchen's view of an order)
- Restaurant Service: manage restaurant profiles and menu data
- Kitchen Service consumes `OrderCreated` from Kafka to create tickets
- Kitchen Service publishes `TicketCreated`, `TicketRejected` to Kafka
- Restaurant Service publishes `MenuUpdated` to Kafka (Kitchen consumes
  this to maintain its local copy of menu data)
- Write Kubernetes manifests and CI/CD for both services

Documentation responsibilities:
- `docs/adr/ADR-003-kitchen-restaurant.md` — explain why these are two
  separate services, and how Kitchen gets Restaurant data without a
  shared database (event-driven data replication)

Things you must be able to explain in a viva:
- Why are Kitchen and Restaurant separate services?
- Kitchen Service needs menu data — how does it get it without calling
  Restaurant Service's database directly?
- What is event-driven data replication and why did you use it here?

---

### Person 3 — Accounting Service Lead

**You own the payment logic. The key story here is isolation for
security and compliance.**

Technical responsibilities:
- Manage consumer accounts and payment authorization
- Consume `OrderCreated` from Kafka to trigger payment authorization
- Publish `PaymentAuthorized`, `PaymentFailed` to Kafka
- Own the `accounts` and `transactions` database schema
- Write Kubernetes manifests and CI/CD pipeline

Documentation responsibilities:
- `docs/adr/ADR-004-accounting.md` — explain why payment logic is
  isolated into its own service (PCI compliance argument, security
  isolation, independent scaling)

Things you must be able to explain in a viva:
- Why is payment processing a separate microservice?
- What is PCI compliance and why does it justify this boundary?
- What happens in the Saga if payment fails after the kitchen has
  already accepted the ticket?

---

### Person 4 — Consumer & Order History Service Lead

**You own two services. Order History is a CQRS read model — the most
conceptually interesting pattern you need to explain.**

Technical responsibilities:
- Consumer Service: manage customer profiles, addresses, authentication
- Order History Service: maintain a read-optimized projection of all
  order data by consuming events from Order, Kitchen, Accounting, and
  Delivery services
- Order History Service is a CQRS view — it is read-only, built from
  events, and owns its own denormalized database schema
- Write Kubernetes manifests and CI/CD for both services

Documentation responsibilities:
- `docs/adr/ADR-005-consumer-cqrs.md` — explain what CQRS is, why
  Order History is a separate service rather than a query on Order
  Service, and what the tradeoffs are

Things you must be able to explain in a viva:
- What is CQRS (Command Query Responsibility Segregation)?
- Why does Order History exist as its own service instead of just
  querying the Order Service?
- What is eventual consistency and how does it apply to the Order
  History view?
- What events does Order History consume and from which services?

---

### Person 5 — Platform & Gateway Lead

**You own the infrastructure everything runs on and the gateway
everything talks through. If your work breaks, the whole project breaks.**

Technical responsibilities:
- Fix and extend Universal AI Gateway for FTGO traffic (see ADR-001)
- Wire two-layer gateway architecture (Universal AI Gateway → FTGO
  API Gateway)
- Write all Kubernetes manifests for the gateway layer
- Set up AWS EKS cluster (`ftgo-eks-cluster`, `ap-south-1`)
- Set up Amazon ECR repositories for all eight services
- Set up GitHub Actions secrets in the repository
- Write the Ingress Controller configuration
- Help every other person debug their Kubernetes manifests
- Write `docker-compose.yml` for local development
- Write `docs/runbook.md` — the authoritative guide to bringing the
  full stack up

Documentation responsibilities:
- `docs/adr/ADR-001-api-gateway.md` — gateway architecture decisions
- `docs/runbook.md` — full cluster setup and deployment guide
- Keep `README.md` up to date as the project evolves

Things you must be able to explain in a viva:
- Why two gateways instead of one?
- What does the Universal AI Gateway add that FTGO's gateway does not?
- What is an Ingress controller and how does it differ from a
  Kubernetes Service?
- What is the difference between a Deployment and a Pod in Kubernetes?
- How does Kubernetes handle a failing service (liveness probes)?

---

## Documents Each Person Maintains

### Mandatory for everyone

| Document | Location | When to update |
|----------|---------|----------------|
| Service ADR | `docs/adr/ADR-00X-<service>.md` | Every time you make an architectural decision |
| Kubernetes manifests | `k8s/<service>/*.yaml` | Every time service config changes |
| GitHub Actions workflow | `.github/workflows/<service>.yml` | When pipeline steps change |
| Service README | `<service>/README.md` | When setup steps change |

### Maintained together

| Document | Who leads | When |
|----------|-----------|------|
| `README.md` | Person 5 | Updated at end of each week |
| `docker-compose.yml` | Person 5 + Person 1 | Week 2 — local dev setup |
| `docs/domain-events.md` | Person 1 leads, all contribute | Week 1 |
| `docs/shared-data-problems.md` | All together | Week 1 |
| `docs/architecture-diagram.png` | All together | Week 3 |
| `docs/adr/ADR-000-master.md` | All together | Final week |
| `docs/runbook.md` | Person 5 | Week 4 |

---

## Weekly Workflow

### Every Monday
- 30-minute sync: what did you finish, what are you doing this week,
  what is blocking you?
- Person 5 merges `dev` → `main` if `dev` is clean

### Every Friday
- Everyone must have at least one PR merged to `dev` for the week
- Update your ADR with any decisions made this week
- Comment on at least one other person's PR

### End of project (final week)
- Feature freeze — no new features, only bug fixes and documentation
- All ADRs must be complete
- ADR-000 master written together
- Full end-to-end test on EKS
- `docs/runbook.md` finalized

---

## Code Review Expectations

When reviewing someone else's PR:

**Do check:**
- Does the service build? (`./gradlew build`)
- Are there any hardcoded secrets, IPs, or passwords?
- Does the Kubernetes manifest have `livenessProbe` and `readinessProbe`?
- Are ConfigMaps used for config and Secrets for credentials?
- Does the CI/CD workflow have the correct path filter?

**Do not block a PR for:**
- Code style preferences (this is a student project, not production)
- Minor naming differences
- Performance optimizations that are not breaking anything

**Comment format:**

```
blocking: <issue that must be fixed before merge>
suggest:  <improvement that would be nice but is not required>
question: <I want to understand this — not necessarily a problem>
```

---

## What To Do When Things Break

### Local build fails

```bash
# Java service
./gradlew clean build   # clean build first
./gradlew dependencies  # check for dependency issues

# Python gateway
pip install -r requirements.txt --upgrade
python -m pytest tests/ -v
```

### Docker Compose service fails to start

```bash
# Check logs for the specific service
docker compose logs <service-name>

# Restart just one service
docker compose restart <service-name>

# Nuclear option — rebuild everything
docker compose down -v
docker compose up --build
```

### Kubernetes pod not starting

```bash
# Check pod status
kubectl get pods -n ftgo

# Check why a pod is failing
kubectl describe pod <pod-name> -n ftgo

# Check pod logs
kubectl logs <pod-name> -n ftgo

# Check events for the namespace
kubectl get events -n ftgo --sort-by='.lastTimestamp'
```

### Git conflicts

```bash
# Do not panic. Do this:
git fetch origin
git rebase origin/dev

# If conflicts appear, resolve them file by file
# Then:
git add <resolved-file>
git rebase --continue

# If you make it worse:
git rebase --abort  # goes back to where you started
```

### CI/CD pipeline failing

1. Check the GitHub Actions log — expand the failing step
2. Most common causes:
   - Missing GitHub Secret
   - Wrong ECR repository name
   - Docker build failing (check your Dockerfile)
   - Kubernetes manifest has a syntax error (`kubectl apply --dry-run=client`)
3. Fix on your feature branch and push — pipeline reruns automatically
