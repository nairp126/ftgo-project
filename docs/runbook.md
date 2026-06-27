# Runbook — FTGO Cluster Setup and Deployment Guide

**Owner:** [Person 5]
**Last updated:** [Date]
**Cluster:** `ftgo-eks-cluster` — AWS EKS, ap-south-1 (Mumbai)

> This is the authoritative guide to bringing the full FTGO stack up
> from scratch. If something is broken in production, start here.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [1. Local Development Setup](#1-local-development-setup)
- [2. AWS Infrastructure Setup](#2-aws-infrastructure-setup)
- [3. EKS Cluster Provisioning](#3-eks-cluster-provisioning)
- [4. Container Registry Setup](#4-container-registry-setup)
- [5. Kubernetes Namespace and Secrets](#5-kubernetes-namespace-and-secrets)
- [6. Deploying Services](#6-deploying-services)
- [7. Verifying the Deployment](#7-verifying-the-deployment)
- [8. Tearing Down](#8-tearing-down)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

Every person needs these installed and verified before touching anything.
See `docs/pre-migration-checklist.md` Phase 1 for installation instructions.

```bash
# Verify all tools are present
java --version          # 17+
docker --version        # 20+
docker compose version  # v2+
kubectl version --client
aws --version
eksctl version
git --version
```

---

## 1. Local Development Setup

Use this to run the full stack on your machine without EKS.
Required before attempting any Kubernetes deployment.

### Start all services locally

```bash
# From the repo root
docker compose up --build

# Start only specific services (faster during development)
docker compose up universal-ai-gateway ftgo-api-gateway ftgo-order-service
```

### Verify each service is healthy

```bash
# Gateway health
curl http://localhost:8000/health

# Order Service (through gateway)
curl http://localhost:8000/api/orders \
  -H "Authorization: Bearer <your-api-key>"

# Direct service access (bypasses gateway — dev only)
curl http://localhost:8081/orders
```

### Stop everything

```bash
docker compose down        # stop containers, keep volumes
docker compose down -v     # stop containers, delete volumes (clean slate)
```

---

## 2. AWS Infrastructure Setup

**Do this once. Person 5 does it. Share credentials securely with the team.**

### Configure AWS CLI

```bash
aws configure
# AWS Access Key ID:     <from AWS console → IAM → Your user → Security credentials>
# AWS Secret Access Key: <same place>
# Default region:        ap-south-1
# Default output format: json

# Verify it works
aws sts get-caller-identity
# Expected output:
# {
#   "Account": "123456789012",
#   "UserId": "...",
#   "Arn": "arn:aws:iam::123456789012:user/your-user"
# }
```

### Set environment variables used throughout this runbook

```bash
export AWS_REGION=ap-south-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity \
  --query Account --output text)
export CLUSTER_NAME=ftgo-eks-cluster
export ECR_BASE=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

echo "Account: $AWS_ACCOUNT_ID"
echo "ECR Base: $ECR_BASE"
```

---

## 3. EKS Cluster Provisioning

> ⚠️ **Do this in the final week only. EKS costs money while running.**
> Estimated cost: ~$0.10/hour for the control plane + ~$0.10/hour
> per t3.medium node = ~$0.40/hour total for a 3-node cluster.
> **Destroy the cluster when not in use.**

### Create the cluster

```bash
eksctl create cluster \
  --name $CLUSTER_NAME \
  --region $AWS_REGION \
  --nodegroup-name standard-workers \
  --node-type t3.medium \
  --nodes 3 \
  --nodes-min 2 \
  --nodes-max 4 \
  --managed

# This takes 15-20 minutes. Get a coffee.
```

### Verify cluster is up

```bash
kubectl get nodes
# Expected: 3 nodes in Ready state

kubectl cluster-info
# Expected: Kubernetes control plane URL
```

### Configure kubectl for the cluster

```bash
aws eks update-kubeconfig \
  --region $AWS_REGION \
  --name $CLUSTER_NAME

# Verify context is set
kubectl config current-context
# Expected: arn:aws:eks:ap-south-1:<account>:cluster/ftgo-eks-cluster
```

### Install the AWS Load Balancer Controller

Required for Ingress to work on EKS.

```bash
# Install cert-manager (dependency)
kubectl apply -f \
  https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Wait for cert-manager to be ready
kubectl wait --namespace cert-manager \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s

# Create IAM policy for the load balancer controller
curl -o aws-load-balancer-controller-policy.json \
  https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/main/docs/install/iam_policy.json

aws iam create-policy \
  --policy-name AWSLoadBalancerControllerIAMPolicy \
  --policy-document file://aws-load-balancer-controller-policy.json

# Create service account
eksctl create iamserviceaccount \
  --cluster=$CLUSTER_NAME \
  --namespace=kube-system \
  --name=aws-load-balancer-controller \
  --role-name AmazonEKSLoadBalancerControllerRole \
  --attach-policy-arn=arn:aws:iam::$AWS_ACCOUNT_ID:policy/AWSLoadBalancerControllerIAMPolicy \
  --approve

# Install the controller via Helm
helm repo add eks https://aws.github.io/eks-charts
helm repo update
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=$CLUSTER_NAME \
  --set serviceAccount.create=false \
  --set serviceAccount.name=aws-load-balancer-controller

# Verify it is running
kubectl get deployment -n kube-system aws-load-balancer-controller
```

---

## 4. Container Registry Setup

### Create ECR repositories

```bash
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
    --region $AWS_REGION \
    --image-scanning-configuration scanOnPush=true
  echo "✅ Created: $SERVICE"
done
```

### Authenticate Docker to ECR

Run this before any manual `docker push`. GitHub Actions handles this
automatically via OIDC — this is for local builds only.

```bash
aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS \
    --password-stdin $ECR_BASE
```

### Build and push an image manually (example — Order Service)

```bash
cd ftgo-order-service

docker build -t ftgo-order-service:local .

docker tag ftgo-order-service:local \
  $ECR_BASE/ftgo-order-service:latest

docker push $ECR_BASE/ftgo-order-service:latest
```

---

## 5. Kubernetes Namespace and Secrets

### Create namespace

```bash
kubectl create namespace ftgo

# Set as default namespace so you don't have to type -n ftgo every time
kubectl config set-context --current --namespace=ftgo
```

### Apply secrets

> ⚠️ Never commit real secret values to Git.
> The `secret.yaml` files in `k8s/` are templates with placeholders.
> Apply real values only via kubectl or GitHub Actions.

```bash
# Create the gateway secret manually (first time only)
kubectl create secret generic universal-ai-gateway-secret \
  --namespace=ftgo \
  --from-literal=DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/gateway" \
  --from-literal=REDIS_URL="redis://redis-host:6379" \
  --from-literal=JWT_SECRET_KEY="your-32-char-random-string-here" \
  --from-literal=AWS_ACCESS_KEY_ID="your-key" \
  --from-literal=AWS_SECRET_ACCESS_KEY="your-secret" \
  --from-literal=S3_BUCKET_NAME="ftgo-audit-logs"

# Repeat for each service's database credentials
kubectl create secret generic ftgo-order-service-secret \
  --namespace=ftgo \
  --from-literal=DATABASE_URL="postgresql://user:pass@host:5433/orders"

# Verify secrets are created (values are not shown)
kubectl get secrets -n ftgo
```

### Apply ConfigMaps

```bash
kubectl apply -f k8s/gateway/configmap.yaml -n ftgo
kubectl apply -f k8s/order-service/configmap.yaml -n ftgo
kubectl apply -f k8s/kitchen-service/configmap.yaml -n ftgo
kubectl apply -f k8s/restaurant-service/configmap.yaml -n ftgo
kubectl apply -f k8s/accounting-service/configmap.yaml -n ftgo
kubectl apply -f k8s/consumer-service/configmap.yaml -n ftgo
kubectl apply -f k8s/order-history-service/configmap.yaml -n ftgo
```

---

## 6. Deploying Services

Deploy in this order. Earlier services have fewer dependencies.

### Step 1 — Deploy Kafka

```bash
kubectl apply -f k8s/kafka/kafka.yaml -n ftgo

# Wait for Kafka to be ready before deploying services
kubectl wait --for=condition=ready pod \
  --selector=app=kafka \
  --timeout=120s \
  -n ftgo
```

### Step 2 — Deploy domain services

```bash
# Apply all service manifests
for SERVICE in \
  consumer-service \
  restaurant-service \
  accounting-service \
  kitchen-service \
  order-service \
  order-history-service; do
  kubectl apply -f k8s/$SERVICE/ -n ftgo
  echo "✅ Applied: $SERVICE"
done
```

### Step 3 — Deploy gateways

```bash
# FTGO internal gateway first
kubectl apply -f k8s/ftgo-api-gateway/ -n ftgo

# Universal AI Gateway second (depends on FTGO gateway being up)
kubectl apply -f k8s/gateway/ -n ftgo
```

### Step 4 — Deploy Ingress

```bash
kubectl apply -f k8s/ingress/ingress-controller.yaml -n ftgo
```

### Step 5 — Wait for all pods to be ready

```bash
kubectl get pods -n ftgo -w
# Wait until all pods show STATUS: Running and READY: 1/1

# Check all deployments
kubectl get deployments -n ftgo
```

---

## 7. Verifying the Deployment

### Get the external load balancer URL

```bash
kubectl get ingress -n ftgo
# Copy the ADDRESS field — this is your external URL
# It looks like: k8s-ftgo-xxx.ap-south-1.elb.amazonaws.com
```

### Health checks

```bash
LB_URL=<your-load-balancer-address>

# Gateway health
curl http://$LB_URL/health
# Expected: {"status": "healthy"}

# FTGO gateway health (proxied through Universal AI Gateway)
curl http://$LB_URL/actuator/health
# Expected: {"status": "UP"}
```

### End-to-end test — Place an order

```bash
# 1. Create a consumer
curl -X POST http://$LB_URL/api/consumers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-api-key>" \
  -d '{"name": "Test User"}'

# 2. Create a restaurant
curl -X POST http://$LB_URL/api/restaurants \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-api-key>" \
  -d '{
    "name": "Test Restaurant",
    "menu": {
      "menuItems": [
        {"id": "1", "name": "Burger", "price": "9.99"}
      ]
    }
  }'

# 3. Place an order
curl -X POST http://$LB_URL/api/orders \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-api-key>" \
  -d '{
    "consumerId": 1,
    "restaurantId": 1,
    "deliveryAddress": {
      "street1": "123 Test St",
      "city": "Mumbai",
      "state": "MH",
      "zip": "400001"
    },
    "lineItems": [
      {"menuItemId": "1", "quantity": 1}
    ]
  }'
# Expected: {"orderId": <id>, "state": "PENDING"}

# 4. Check order status (tests API composition)
curl http://$LB_URL/api/orders/<orderId> \
  -H "Authorization: Bearer <your-api-key>"
# Expected: order + ticket + delivery + billing combined in one response
```

### Check Prometheus metrics

```bash
# Port-forward to FTGO gateway to check metrics locally
kubectl port-forward \
  deployment/ftgo-api-gateway 9090:8080 -n ftgo

curl http://localhost:9090/actuator/prometheus
```

### Check distributed traces (Zipkin)

```bash
# Port-forward to Zipkin
kubectl port-forward deployment/zipkin 9411:9411 -n ftgo

# Open in browser
open http://localhost:9411
```

---

## 8. Tearing Down

> **Always destroy the EKS cluster when not actively using it.**
> A running 3-node cluster costs ~$0.40/hour = ~$300/month.

```bash
# Delete all Kubernetes resources first
kubectl delete namespace ftgo

# Destroy the EKS cluster
eksctl delete cluster \
  --name $CLUSTER_NAME \
  --region $AWS_REGION

# Verify it is gone
aws eks list-clusters --region $AWS_REGION
# Expected: empty list

# ECR repositories persist (no cost unless storing images)
# Delete if no longer needed:
for SERVICE in "${SERVICES[@]}"; do
  aws ecr delete-repository \
    --repository-name "$SERVICE" \
    --region $AWS_REGION \
    --force
done
```

---

## Troubleshooting

### Pod stuck in Pending state

```bash
kubectl describe pod <pod-name> -n ftgo
# Look for "Events" section at the bottom
# Common cause: insufficient CPU/memory — node cannot schedule the pod
# Fix: check resource requests in deployment.yaml, reduce if too high
```

### Pod stuck in CrashLoopBackOff

```bash
kubectl logs <pod-name> -n ftgo
kubectl logs <pod-name> -n ftgo --previous  # logs from crashed container
# Common causes:
# - Wrong DATABASE_URL in secret
# - Service cannot connect to Kafka (check Kafka is running)
# - Missing environment variable
```

### ImagePullBackOff

```bash
kubectl describe pod <pod-name> -n ftgo
# Look for: "Failed to pull image"
# Common causes:
# - ECR image does not exist (CI/CD pipeline did not push)
# - Node does not have ECR pull permissions
# Fix: verify IAM role attached to EKS node group has ECR read permissions
```

### Gateway returns 502 Bad Gateway

```bash
# Universal AI Gateway cannot reach FTGO gateway
# Check FTGO gateway is running
kubectl get pods -n ftgo | grep ftgo-api-gateway

# Check the service DNS resolves
kubectl run debug --image=busybox --restart=Never -n ftgo -- \
  nslookup ftgo-api-gateway
kubectl logs debug -n ftgo
kubectl delete pod debug -n ftgo
```

### Kafka consumer not receiving messages

```bash
# Check Kafka topics exist
kubectl exec -it deployment/kafka -n ftgo -- \
  kafka-topics.sh --list --bootstrap-server localhost:9092

# Check consumer group lag
kubectl exec -it deployment/kafka -n ftgo -- \
  kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group ftgo-order-service
```

### Out of disk space on nodes

```bash
# Check node disk usage
kubectl describe nodes | grep -A5 "Allocated resources"

# Clean up old Docker images on nodes
# This requires SSH to the EC2 nodes — use AWS Systems Manager Session Manager
```
