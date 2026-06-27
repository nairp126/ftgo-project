# Pre-Migration Checklist

> Complete every item in this checklist **before** writing a single line
> of microservice code. Skipping steps here causes debugging pain later.
> Work through this as a group in your first week.

---

## Table of Contents

- [Phase 0 — Understand the Monolith](#phase-0--understand-the-monolith)
- [Phase 1 — Local Environment Setup](#phase-1--local-environment-setup)
- [Phase 2 — Repository Setup](#phase-2--repository-setup)
- [Phase 3 — Monolith Analysis](#phase-3--monolith-analysis)
- [Phase 4 — Architecture Decisions](#phase-4--architecture-decisions)
- [Phase 5 — Infrastructure Preparation](#phase-5--infrastructure-preparation)
- [Phase 6 — Team Alignment](#phase-6--team-alignment)

---

## Phase 0 — Understand the Monolith

These are non-negotiable. Everyone must do these independently, not as a
group watch-along.

### Reading (do before your first team meeting)

- [ ] Read Chapters 1–2 of *Microservices Patterns* by Chris Richardson
      (covers why monoliths break down and the decomposition approach)
- [ ] Read Chapter 4 (Saga pattern — critical for Order Service)
- [ ] Read Chapter 7 (CQRS — critical for Order History Service)
- [ ] Read the FTGO monolith README:
      https://github.com/microservices-patterns/ftgo-monolith
- [ ] Read the FTGO application README (the decomposed reference):
      https://github.com/microservices-patterns/ftgo-application

### Questions every person must be able to answer before Week 2

- [ ] What does the FTGO application do? (food delivery — explain the
      full user journey from placing an order to delivery)
- [ ] What tables exist in the monolith database? (run the app and inspect)
- [ ] What is a Saga pattern and why do we need it when we split
      Order + Kitchen + Accounting into separate services?
- [ ] What is CQRS and why does Order History exist as a separate
      service instead of just querying the Order Service?
- [ ] What is the Strangler Fig pattern and why are we using it instead
      of a big-bang rewrite?

---

## Phase 1 — Local Environment Setup

Every person completes this on their own machine before the first
team coding session.

### Required tools

```bash
# Check each of these works on your machine after installing

java --version        # must be Java 17+
mvn --version         # OR ./gradlew --version inside a service folder
docker --version      # Docker Desktop — must be running
docker compose version # v2+ (note: no hyphen)
kubectl version --client
git --version
```

### Installation instructions (Windows)

**Java 17**
```
Download from: https://adoptium.net/
Choose: Temurin 17 LTS
Add to PATH: C:\Program Files\Eclipse Adoptium\jdk-17\bin
Verify: java --version
```

**Docker Desktop**
```
Download from: https://www.docker.com/products/docker-desktop/
Enable WSL 2 backend when prompted (required on Windows)
After install, open Docker Desktop and wait for it to fully start
Verify: docker run hello-world
```

**kubectl**
```
Download from: https://dl.k8s.io/release/v1.29.0/bin/windows/amd64/kubectl.exe
Rename to kubectl.exe and move to C:\Windows\System32\
Verify: kubectl version --client
```

**AWS CLI**
```
Download from: https://aws.amazon.com/cli/
Run the MSI installer
Verify: aws --version
```

**Python 3.12 (Person 5 only)**
```
Download from: https://www.python.org/downloads/
Check "Add to PATH" during installation
Verify: python --version
```

### Installation instructions (Mac)

```bash
# Install Homebrew first if not present
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Then install everything
brew install openjdk@17
brew install --cask docker
brew install kubectl
brew install awscli
brew install python@3.12   # Person 5 only
```

### Verify Docker is working

```bash
# This must succeed on everyone's machine
docker run --rm hello-world

# This must also work
docker compose version
```

---

## Phase 2 — Repository Setup

**One person (Person 5) does the setup. Everyone else clones.**

### Step 1 — Create the GitHub repository

```
1. Go to github.com
2. Create a new repository
   Name:     ftgo-devops-project
   Visibility: Private
   Initialize with README: Yes
3. Add all 5 team members as collaborators
   Settings → Collaborators → Add people
```

### Step 2 — Initialize the monorepo structure (Person 5)

```bash
git clone https://github.com/<your-org>/ftgo-devops-project.git
cd ftgo-devops-project

# Add the FTGO monolith as reference (do not modify this folder)
git subtree add \
  --prefix ftgo-monolith \
  https://github.com/microservices-patterns/ftgo-monolith \
  master --squash

# Create all folder scaffolding
mkdir -p ftgo-order-service
mkdir -p ftgo-kitchen-service
mkdir -p ftgo-restaurant-service
mkdir -p ftgo-accounting-service
mkdir -p ftgo-consumer-service
mkdir -p ftgo-order-history-service
mkdir -p universal-ai-gateway

mkdir -p k8s/{gateway,order-service,kitchen-service,restaurant-service,\
accounting-service,consumer-service,order-history-service,kafka,ingress}

mkdir -p docs/adr
mkdir -p .github/workflows

# Copy service code from the ftgo-application reference
# Each person will later do this for their own service
# For now Person 5 seeds the structure with empty .gitkeep files
touch k8s/gateway/.gitkeep
touch k8s/order-service/.gitkeep
touch k8s/kitchen-service/.gitkeep
touch k8s/restaurant-service/.gitkeep
touch k8s/accounting-service/.gitkeep
touch k8s/consumer-service/.gitkeep
touch k8s/order-history-service/.gitkeep
touch k8s/kafka/.gitkeep

git add .
git commit -m "chore: initialize monorepo structure"
git push origin main
```

### Step 3 — Each person copies their service

Each person runs this for their own service:

```bash
# Example for Person 1 — Order Service
# Download the service folder from the ftgo-application repo
curl -L https://github.com/microservices-patterns/ftgo-application/archive/refs/heads/master.zip \
  -o ftgo-application.zip
unzip ftgo-application.zip

# Copy your specific service into the monorepo
cp -r ftgo-application-master/ftgo-order-service ./ftgo-order-service/
rm -rf ftgo-application-master ftgo-application.zip

git checkout -b feat/order-service
git add ftgo-order-service/
git commit -m "feat(order-service): seed service from ftgo-application reference"
git push origin feat/order-service
# Then open a PR to dev branch — do not merge to main yet
```

### Step 4 — Set up branch protection (Person 5)

```
GitHub → Settings → Branches → Add rule

Branch name pattern: main
  ✅ Require a pull request before merging
  ✅ Require at least 1 approval
  ✅ Require status checks to pass before merging

Branch name pattern: dev
  ✅ Require a pull request before merging
```

### Step 5 — Everyone clones and verifies

```bash
git clone https://github.com/<your-org>/ftgo-devops-project.git
cd ftgo-devops-project

# Verify you can see the structure
ls -la
# You should see: ftgo-monolith/, docs/, k8s/, .github/, README.md
```

---

## Phase 3 — Monolith Analysis

**Everyone does this. Do not skip it. You cannot make good service boundary
decisions without understanding what you are breaking apart.**

### Step 1 — Run the monolith locally

```bash
cd ftgo-monolith

# Start dependencies
docker compose up -d mysql

# Build and run the monolith
./gradlew build
./gradlew bootRun
```

Expected: Application starts on port 8080. You should be able to place
a test order via the API.

If it fails to start, check:
- Java version (`java --version` must be 17+)
- MySQL container is healthy (`docker compose ps`)
- Port 8080 is not already in use

### Step 2 — Map the database schema

Everyone opens the monolith database and maps every table:

```bash
# Connect to the running MySQL instance
docker exec -it ftgo-monolith-mysql-1 mysql -u root -p ftgo

# List all tables
SHOW TABLES;

# For each table, describe its structure
DESCRIBE orders;
DESCRIBE consumers;
DESCRIBE restaurants;
# ... and so on for every table
```

**Document this in a shared Google Sheet or Notion page with columns:**
- Table name
- Columns
- Foreign keys (which other tables does it reference?)
- Who owns this table? (which future service?)
- Shared? (does more than one future service need this data?)

This database mapping is the single most important pre-migration exercise.
Every service boundary dispute in Week 2 will reference this document.

### Step 3 — Map the domain events

For each action in the monolith (place order, confirm order, create
restaurant, etc.), trace through the code and document:

- What triggered it (HTTP endpoint)
- What database tables it wrote to
- What it would need to publish as an event in a microservices world
- What other services would need to consume that event

Create a file `docs/domain-events.md` with this mapping.
Person 1 leads this since Order is the most event-heavy service,
but everyone contributes their own service's events.

### Step 4 — Identify shared data problems

Look at your database schema map and find:

- [ ] Tables that multiple future services will need to read
- [ ] Foreign keys that cross service boundaries
      (e.g. an orders table referencing a consumers table — these will
      be in different databases after migration)
- [ ] Any tables that are genuinely ambiguous about ownership

Document each shared data problem in `docs/shared-data-problems.md`.
For each one, write your proposed solution (event-driven replication,
API call, CQRS view, etc.). These become the hardest parts of your ADRs.

---

## Phase 4 — Architecture Decisions

**Do this as a group meeting. Allow 2–3 hours. Do not rush it.**

### Meeting agenda

**Part 1 — Service boundary confirmation (60 min)**

Go through each service and confirm:
- Exactly which database tables it owns
- Exactly which Kafka topics it publishes to
- Exactly which Kafka topics it consumes from
- Its REST API surface (what endpoints does it expose?)

Write decisions on a whiteboard or shared doc. Disagreements are good —
they become ADR content.

**Part 2 — Cross-cutting decisions (60 min)**

Decide as a group on these questions. Document the decision and the
reason — not just what you decided but why:

- [ ] **Database technology:** PostgreSQL for all services? 
      (Recommendation: yes, keep it consistent for a student project)
- [ ] **Messaging:** Kafka topics naming convention?
      Suggestion: `ftgo.<service>.<event>` e.g. `ftgo.order.created`
- [ ] **API versioning:** Do all services use `/api/v1/` prefix?
- [ ] **Authentication:** Does auth happen at the gateway only, or do
      services also validate tokens?
      (Recommendation: gateway only — services trust X-User-ID header)
- [ ] **Service ports:** Assign a unique local dev port to each service
      to avoid conflicts (see table below)
- [ ] **Docker image naming:** Convention for ECR image names?
      Suggestion: `ftgo/<service-name>:latest`

**Recommended local port assignments:**

| Service | Local Port |
|---------|-----------|
| Universal AI Gateway | 8000 |
| FTGO API Gateway | 8080 |
| Order Service | 8081 |
| Kitchen Service | 8082 |
| Restaurant Service | 8083 |
| Accounting Service | 8084 |
| Consumer Service | 8085 |
| Order History Service | 8086 |
| Kafka | 9092 |
| Zookeeper | 2181 |
| PostgreSQL (Order) | 5433 |
| PostgreSQL (Kitchen) | 5434 |
| PostgreSQL (Restaurant) | 5435 |
| PostgreSQL (Accounting) | 5436 |
| PostgreSQL (Consumer) | 5437 |
| PostgreSQL (History) | 5438 |
| Redis | 6379 |

**Part 3 — Each person writes their first ADR draft (30 min)**

Using `docs/adr/ADR-TEMPLATE.md`, each person writes the Context and
Decision Drivers sections for their service. You do not need the full
ADR yet — just the context and the questions you have not answered yet.

---

## Phase 5 — Infrastructure Preparation

**Person 5 leads. Others observe or assist.**

### AWS account setup

```bash
# Configure AWS CLI with your credentials
aws configure
# AWS Access Key ID: <from AWS console>
# AWS Secret Access Key: <from AWS console>
# Default region name: ap-south-1
# Default output format: json

# Verify access
aws sts get-caller-identity
```

### Create ECR repositories (one per service)

```bash
# Run this script to create all ECR repos at once
REGION=ap-south-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

SERVICES=(
  "universal-ai-gateway"
  "ftgo-api-gateway"
  "ftgo-order-service"
  "ftgo-kitchen-service"
  "ftgo-restaurant-service"
  "ftgo-accounting-service"
  "ftgo-consumer-service"
  "ftgo-order-history-service"
)

for SERVICE in "${SERVICES[@]}"; do
  aws ecr create-repository \
    --repository-name "$SERVICE" \
    --region $REGION \
    --image-scanning-configuration scanOnPush=true
  echo "Created ECR repo: $SERVICE"
done

echo "ECR Base URL: $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
```

Save the ECR Base URL — everyone needs it for their Dockerfiles and
GitHub Actions workflows.

### Create EKS cluster

> ⚠️ **Do this in the final week of the project, not now.**
> EKS costs money while running. Provision it when you are ready to deploy.

```bash
# Install eksctl if not present
# Windows: choco install eksctl
# Mac: brew install eksctl

eksctl create cluster \
  --name ftgo-eks-cluster \
  --region ap-south-1 \
  --nodegroup-name standard-workers \
  --node-type t3.medium \
  --nodes 3 \
  --nodes-min 2 \
  --nodes-max 4 \
  --managed

# Verify cluster is up
kubectl get nodes
```

### Set up GitHub Actions secrets

Go to your GitHub repo → Settings → Secrets and variables → Actions

Add these secrets (Person 5 adds all of them):

| Secret Name | Value |
|-------------|-------|
| `AWS_ACCOUNT_ID` | Your AWS account ID |
| `AWS_REGION` | `ap-south-1` |
| `EKS_CLUSTER_NAME` | `ftgo-eks-cluster` |
| `ECR_REGISTRY` | `<account-id>.dkr.ecr.ap-south-1.amazonaws.com` |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `JWT_SECRET_KEY` | Random 32+ character string |
| `AWS_ACCESS_KEY_ID` | AWS access key (for CI/CD) |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key (for CI/CD) |

---

## Phase 6 — Team Alignment

Complete this before anyone starts coding their service.

### Checklist

- [ ] Everyone has read the pre-migration reading list (Phase 0)
- [ ] Everyone can run the monolith locally (Phase 3, Step 1)
- [ ] Database schema is fully mapped and in the shared doc
- [ ] Domain events document is drafted (`docs/domain-events.md`)
- [ ] Shared data problems are documented (`docs/shared-data-problems.md`)
- [ ] Service boundaries confirmed in the group meeting (Phase 4)
- [ ] Port assignments agreed and documented
- [ ] Kafka topic naming convention agreed
- [ ] Everyone has the repo cloned and their branch created
- [ ] Branch protection rules are set on `main` and `dev`
- [ ] ECR repositories created (Person 5)
- [ ] GitHub Actions secrets added (Person 5)
- [ ] Every person has written their ADR Context section

### Definition of "ready to start coding"

You are ready to start extracting your service when:

1. You can answer: "What database tables does my service own and why?"
2. You can answer: "What Kafka topics does my service publish and consume?"
3. You have the service running locally from the `ftgo-application` reference
4. Your ADR Context and Decision Drivers sections are written
5. Your `feat/<service>` branch is created and pushed

**If you cannot answer points 1 and 2, go back to Phase 3.**
