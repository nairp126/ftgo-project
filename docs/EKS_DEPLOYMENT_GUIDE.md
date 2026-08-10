# FTGO EKS Deployment Guide
## Complete Step-by-Step Deployment from a Fresh Windows Machine

> **Project:** Containerized Microservices Deployment on Kubernetes
> **Cluster:** `ftgo-eks-cluster` — AWS EKS, ap-south-1 (Mumbai)
> **Author:** [Person 5]
> **Last deployed:** July 2026
> **Status:** Verified end-to-end on live EKS (7/7 tests passing)

This is the **single authoritative reference** for deploying FTGO on AWS EKS.
It covers both a first-time deployment from a completely fresh machine and
subsequent redeployments after teardown.

---

## How to Use This Guide

| Scenario | Sections to Run |
|----------|----------------|
| **First-time setup** (fresh AWS account, new machine) | All sections — §1 through §15 in order |
| **Redeploy after teardown** (cluster was destroyed, everything else intact) | Start at **§6** — skip §1–5 (one-time setup already done) |
| **Just verifying** (cluster is running, want to re-run tests) | §13 only |

### One-Time Setup Sections (do these once per account/machine)

| Section | What It Does | When to Repeat |
|---------|-------------|----------------|
| §1 — Prerequisites | AWS account, GitHub access | Never |
| §2 — Tool Installation | AWS CLI, Docker, kubectl, eksctl, Helm | Only on a new machine |
| §3 — AWS Configuration | `aws configure` with access keys | Only on a new machine |
| §4 — AWS Infrastructure | ECR repos, S3 bucket, GitHub OIDC provider, IAM role | Never — ECR repos and IAM role survive teardown |
| §5 — GitHub Secrets | Add 9 secrets in GitHub Settings | Never — secrets persist in GitHub |

### Per-Cluster Sections (run every time you create a new cluster)

| Section | What It Does |
|---------|-------------|
| §6 — EKS Cluster | `eksctl create cluster` — provisions VPC, EC2, control plane |
| §7 — Cluster Setup | EBS CSI, StorageClass, namespace, LBC, PostgreSQL, Redis, Kafka |
| §8 — Database Setup | Create 7 application databases inside PostgreSQL |
| §9 — Secrets | Committed secrets apply via `kubectl apply`; patch AWS credential secret |
| §10 — Build & Push | **Skip if CI/CD has run** — GitHub Actions pushes images to ECR on every `git push`. Only run manually if ECR repos are empty (first-ever deploy with no prior CI run). |
| §11 — Deploy Services | `kubectl apply -f k8s/` for all 8 services |
| §12 — Ingress | Deploy ALB ingress; wait for DNS; update LB URL in demo scripts |
| §13 — Verify | Run `demo-day-check.py` (14/14 PASS) and `demo-commands.py` |
| §14 — Teardown | `python teardown.py` — destroys all AWS resources after demo |

---

## Table of Contents

1. [Prerequisites — Accounts and Access](#1-prerequisites)
2. [Tool Installation](#2-tool-installation)
3. [AWS Configuration](#3-aws-configuration)
4. [AWS Infrastructure Setup](#4-aws-infrastructure-setup)
5. [GitHub Repository Setup](#5-github-repository-setup)
6. [EKS Cluster Provisioning](#6-eks-cluster-provisioning)
7. [Cluster Infrastructure Setup](#7-cluster-infrastructure-setup)
8. [Database Setup](#8-database-setup)
9. [Kubernetes Secrets](#9-kubernetes-secrets)
10. [Build and Push Docker Images](#10-build-and-push-docker-images)
11. [Deploy Services](#11-deploy-services)
12. [Ingress and External Access](#12-ingress-and-external-access)
13. [End-to-End Verification](#13-end-to-end-verification)
14. [Teardown](#14-teardown)
15. [Cost Reference](#15-cost-reference)

---

## 1. Prerequisites

Before starting, ensure you have:

- [ ] AWS account with admin or power user IAM permissions
- [ ] GitHub account with access to the `ftgo-project` repository
- [ ] AWS Access Key ID and Secret Access Key
  - Get from: AWS Console → your name → Security credentials
    → Access keys → Create access key → CLI → Download CSV
- [ ] Windows 11 machine with PowerShell 5.1 or higher
- [ ] At least 20GB free disk space (Docker images are large)
- [ ] Stable internet connection (image pushes are 400-600MB each)

> ⚠️ **Cost warning:** EKS costs approximately ₹2,500-3,000 per day
> for a 3-node t3.medium cluster. Provision only when ready to deploy
> immediately. Run teardown immediately after demo.

---

## 2. Tool Installation

Open PowerShell **as Administrator** for all installation steps.

### 2.1 — AWS CLI

Download and install from the official MSI:

```
https://awscli.amazonaws.com/AWSCLIV2.msi
```

Run the MSI installer, accept defaults.

Verify:
```powershell
aws --version
# Expected: aws-cli/2.x.x
```

### 2.2 — Docker Desktop

Download from:
```
https://www.docker.com/products/docker-desktop/
```

During installation:
- Enable WSL 2 backend when prompted
- After install, open Docker Desktop and wait for it to fully start
- The whale icon in the system tray must be steady (not animating)

Verify:
```powershell
docker --version
# Expected: Docker version 29.x.x
```

### 2.3 — kubectl

```powershell
# Run as Administrator
Invoke-WebRequest `
    -Uri "https://dl.k8s.io/release/v1.29.0/bin/windows/amd64/kubectl.exe" `
    -OutFile "C:\Windows\System32\kubectl.exe"

kubectl version --client
# Expected: Client Version: v1.29.x
```

### 2.4 — eksctl

```powershell
# Run as Administrator
Invoke-WebRequest `
    -Uri "https://github.com/eksctl-io/eksctl/releases/latest/download/eksctl_Windows_amd64.zip" `
    -OutFile "eksctl.zip"

Expand-Archive -Path "eksctl.zip" -DestinationPath "C:\eksctl" -Force
Move-Item -Path "C:\eksctl\eksctl.exe" -Destination "C:\Windows\System32\eksctl.exe" -Force

eksctl version
# Expected: 0.229.x or higher
```

### 2.5 — Helm

```powershell
# Run as Administrator
Invoke-WebRequest `
    -Uri "https://get.helm.sh/helm-v3.17.0-windows-amd64.zip" `
    -OutFile "helm.zip"

Expand-Archive -Path "helm.zip" -DestinationPath "C:\helm" -Force
Move-Item -Path "C:\helm\windows-amd64\helm.exe" `
    -Destination "C:\Windows\System32\helm.exe" -Force

helm version
# Expected: version.BuildInfo{Version:"v3.17.0"...}
```

### 2.6 — Verify All Tools

```powershell
aws --version
eksctl version
kubectl version --client
helm version
docker --version
```

All five must return version numbers before proceeding.

---

## 3. AWS Configuration

### 3.1 — Configure AWS CLI

```powershell
aws configure
```

Enter when prompted:
```
AWS Access Key ID:     <from your downloaded CSV>
AWS Secret Access Key: <from your downloaded CSV>
Default region name:   ap-south-1
Default output format: json
```

### 3.2 — Verify Access

```powershell
aws sts get-caller-identity
```

Expected output:
```json
{
    "UserId": "AIDAXXXXXXXXXXXXXXXXX",
    "Account": "120569617989",
    "Arn": "arn:aws:iam::120569617989:user/your-username"
}
```

### 3.3 — Set Variables

Run these in every new PowerShell session — they are used throughout:

```powershell
$ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$REGION = "ap-south-1"
$CLUSTER_NAME = "ftgo-eks-cluster"
$ECR = "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

echo "Account: $ACCOUNT_ID"
echo "Region:  $REGION"
echo "ECR:     $ECR"
```

---

## 4. AWS Infrastructure Setup

### 4.1 — Create ECR Repositories

```powershell
$SERVICES = @(
    "universal-ai-gateway",
    "ftgo-api-gateway",
    "ftgo-order-service",
    "ftgo-kitchen-service",
    "ftgo-restaurant-service",
    "ftgo-accounting-service",
    "ftgo-consumer-service",
    "ftgo-order-history-service"
)

foreach ($SERVICE in $SERVICES) {
    aws ecr create-repository `
        --repository-name $SERVICE `
        --region $REGION `
        --image-scanning-configuration scanOnPush=true
    Write-Host "Created ECR repo: $SERVICE"
}
```

Verify:
```powershell
aws ecr describe-repositories --region $REGION `
    --query 'repositories[].repositoryName' --output table
```

Expected: table showing all 8 repository names.

### 4.2 — Create S3 Bucket for Audit Logs

```powershell
aws s3 mb s3://ftgo-audit-logs-$ACCOUNT_ID --region $REGION

# Verify
aws s3 ls | Select-String "ftgo-audit-logs"
```

### 4.3 — Create GitHub OIDC Provider

This allows GitHub Actions to authenticate with AWS without
storing long-lived credentials in GitHub secrets.

```powershell
aws iam create-open-id-connect-provider `
    --url https://token.actions.githubusercontent.com `
    --client-id-list sts.amazonaws.com `
    --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1

# Verify
aws iam list-open-id-connect-providers
# Expected: one entry with token.actions.githubusercontent.com
```

### 4.4 — Create GitHub Actions IAM Role

Replace `YOUR_GITHUB_ORG` and `YOUR_REPO_NAME` with your values:

```powershell
$GITHUB_ORG = "nairp126"
$GITHUB_REPO = "ftgo-project"

@"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::$($ACCOUNT_ID):oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:${GITHUB_ORG}/${GITHUB_REPO}:*"
        }
      }
    }
  ]
}
"@ | Out-File -FilePath "github-trust-policy.json" -Encoding ASCII -NoNewline

aws iam create-role `
    --role-name GitHubActionsRole `
    --assume-role-policy-document file://github-trust-policy.json

aws iam attach-role-policy `
    --role-name GitHubActionsRole `
    --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess

aws iam attach-role-policy `
    --role-name GitHubActionsRole `
    --policy-arn arn:aws:iam::aws:policy/AmazonEKSClusterPolicy

aws iam attach-role-policy `
    --role-name GitHubActionsRole `
    --policy-arn arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy

# Get the role ARN — save this for GitHub secrets
aws iam get-role --role-name GitHubActionsRole `
    --query 'Role.Arn' --output text
```

---

## 5. GitHub Repository Setup

Go to your GitHub repo → Settings → Secrets and variables
→ Actions → New repository secret

Generate a JWT secret key:
```powershell
$JWT_KEY = -join ((65..90)+(97..122)+(48..57) | Get-Random -Count 32 | %{[char]$_})
echo "JWT Key: $JWT_KEY"
# Copy this value
```

Add these secrets:

```
Secret Name              Value
-----------              -----
AWS_ACCOUNT_ID           120569617989
AWS_REGION               ap-south-1
EKS_CLUSTER_NAME         ftgo-eks-cluster
ECR_REGISTRY             120569617989.dkr.ecr.ap-south-1.amazonaws.com
AWS_ROLE_ARN             arn:aws:iam::120569617989:role/GitHubActionsRole
S3_BUCKET_NAME           ftgo-audit-logs-120569617989
JWT_SECRET_KEY           <output from the command above>
AWS_ACCESS_KEY_ID        <your access key>
AWS_SECRET_ACCESS_KEY    <your secret key>
```

Verify via GitHub CLI (optional):
```powershell
gh secret list
# Must show all 9 secrets
```

---

## 6. EKS Cluster Provisioning

> ⚠️ Only run this when ready to deploy immediately.
> The cluster costs money from the moment it is created.

### 6.1 — Create the Cluster

```powershell
eksctl create cluster `
    --name $CLUSTER_NAME `
    --region $REGION `
    --nodegroup-name standard-workers `
    --node-type t3.medium `
    --nodes 3 `
    --nodes-min 2 `
    --nodes-max 4 `
    --managed
```

This takes 15-20 minutes. You will see CloudFormation events
streaming. Do not interrupt it.

What it creates behind the scenes:
- VPC (192.168.0.0/16) with public and private subnets
  across 3 availability zones (ap-south-1a, 1b, 1c)
- EKS control plane (API server, etcd, scheduler)
- 3 t3.medium EC2 worker nodes
- Required IAM roles for cluster and nodes
- Updates `~/.kube/config` automatically

### 6.2 — Verify Cluster

```powershell
kubectl get nodes
# Expected: 3 nodes all showing STATUS = Ready

kubectl cluster-info
# Expected: Kubernetes control plane URL shown
```

### 6.3 — Associate OIDC Provider with Cluster

Required for pods to assume IAM roles:

```powershell
eksctl utils associate-iam-oidc-provider `
    --cluster $CLUSTER_NAME `
    --region $REGION `
    --approve
```

---

## 7. Cluster Infrastructure Setup

### 7.1 — Install EBS CSI Driver

Required for persistent storage (PostgreSQL needs EBS volumes).
Without this, PostgreSQL pods stay in Pending state forever.

```powershell
# Create IAM role for EBS CSI Driver
eksctl create iamserviceaccount `
    --name ebs-csi-controller-sa `
    --namespace kube-system `
    --cluster $CLUSTER_NAME `
    --region $REGION `
    --attach-policy-arn arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy `
    --approve `
    --role-only `
    --role-name AmazonEKS_EBS_CSI_DriverRole

# Install the addon
aws eks create-addon `
    --cluster-name $CLUSTER_NAME `
    --addon-name aws-ebs-csi-driver `
    --region $REGION `
    --service-account-role-arn arn:aws:iam::${ACCOUNT_ID}:role/AmazonEKS_EBS_CSI_DriverRole

# Wait 60 seconds then verify
Start-Sleep -Seconds 60
aws eks describe-addon `
    --cluster-name $CLUSTER_NAME `
    --addon-name aws-ebs-csi-driver `
    --region $REGION `
    --query 'addon.status' --output text
# Expected: ACTIVE
```

### 7.2 — Set Default StorageClass

```powershell
kubectl patch storageclass gp2 `
    -p '{\"metadata\":{\"annotations\":{\"storageclass.kubernetes.io/is-default-class\":\"true\"}}}'

kubectl get storageclass
# Expected: gp2 shows (default)
```

### 7.3 — Create Namespace

```powershell
kubectl create namespace ftgo
kubectl config set-context --current --namespace=ftgo

kubectl get namespace ftgo
# Expected: ftgo   Active
```

### 7.4 — Install AWS Load Balancer Controller

Required for Ingress to create actual AWS Application Load Balancers.

```powershell
# Create IAM policy
Invoke-WebRequest `
    -Uri "https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/main/docs/install/iam_policy.json" `
    -OutFile "alb-policy.json"

aws iam create-policy `
    --policy-name AWSLoadBalancerControllerIAMPolicy `
    --policy-document file://alb-policy.json `
    --region $REGION

# Create service account
eksctl create iamserviceaccount `
    --cluster=$CLUSTER_NAME `
    --namespace=kube-system `
    --name=aws-load-balancer-controller `
    --role-name AmazonEKSLoadBalancerControllerRole `
    --attach-policy-arn=arn:aws:iam::${ACCOUNT_ID}:policy/AWSLoadBalancerControllerIAMPolicy `
    --approve `
    --region $REGION

# Install via Helm
helm repo add eks https://aws.github.io/eks-charts
helm repo update

helm install aws-load-balancer-controller `
    eks/aws-load-balancer-controller `
    -n kube-system `
    --set clusterName=$CLUSTER_NAME `
    --set serviceAccount.create=false `
    --set serviceAccount.name=aws-load-balancer-controller

# Verify
kubectl get deployment -n kube-system aws-load-balancer-controller
# Expected: READY 2/2
```

### 7.5 — Install PostgreSQL via Helm

```powershell
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

helm install ftgo-postgres bitnami/postgresql `
    --namespace=ftgo `
    --set auth.postgresPassword=mysecretpassword `
    --set auth.database=ftgo

# Watch until Running
kubectl get pods -n ftgo -w
# Wait for: ftgo-postgres-postgresql-0   1/1   Running
```

If pod stays Pending — check StorageClass was set as default
in Step 7.2.

### 7.6 — Install Redis via Helm

```powershell
helm install ftgo-redis bitnami/redis `
    --namespace=ftgo `
    --set auth.enabled=false

# Watch until Running
kubectl get pods -n ftgo -w
# Wait for: ftgo-redis-master-0   1/1   Running
```

### 7.7 — Install Kafka (KRaft Mode)

> Important: Use `enableServiceLinks: false` in the Kafka pod spec.
> Without it, Kubernetes injects `KAFKA_PORT=tcp://...` which
> Confluent's entrypoint misinterprets and crashes.
> See DEPLOYMENT_ERRORS.md Issue 10 for full explanation.

Apply the Kafka manifest:
```powershell
kubectl apply -f k8s/kafka/kafka.yaml -n ftgo

kubectl get pods -n ftgo -w
# Wait for: kafka-xxxxx   1/1   Running
```

Verify Kafka topics are auto-created after services start:
```powershell
kubectl exec -it -n ftgo `
    $(kubectl get pod -n ftgo -l app=kafka -o jsonpath='{.items[0].metadata.name}') `
    -- kafka-topics.sh --list --bootstrap-server localhost:9092
```

---

## 8. Database Setup

Create a separate database for each service inside the single
PostgreSQL instance:

```powershell
$PG_POD = $(kubectl get pod -n ftgo `
    -l app.kubernetes.io/name=postgresql `
    -o jsonpath='{.items[0].metadata.name}')

$DATABASES = @(
    "orders",
    "kitchen",
    "restaurant",
    "accounting",
    "consumers",
    "orderhistory",
    "gateway"
)

foreach ($DB in $DATABASES) {
    kubectl exec -n ftgo $PG_POD `
        -- env PGPASSWORD=mysecretpassword psql -U postgres `
        -c "CREATE DATABASE $DB;"
    Write-Host "Created database: $DB"
}

# Verify all databases
kubectl exec -n ftgo $PG_POD `
    -- env PGPASSWORD=mysecretpassword psql -U postgres -c "\l"
```

Expected: orders, kitchen, restaurant, accounting, consumers,
orderhistory, gateway all listed.

---

## 9. Kubernetes Secrets

### 9.1 — Generate JWT Key

```powershell
$JWT_KEY = -join ((65..90)+(97..122)+(48..57) | Get-Random -Count 32 | %{[char]$_})
echo "JWT Key: $JWT_KEY"
# Save this value — also add it to GitHub secrets as JWT_SECRET_KEY
```

### 9.2 — Apply Committed Secrets

Most secrets are already committed to the repository as base64-encoded
`secret.yaml` files. Apply them now as part of the manifest apply:

```powershell
# Applied automatically in §11 via kubectl apply -f k8s/<service>/
# The following secrets are committed and require no manual creation:
#   k8s/gateway/secret.yaml              → universal-ai-gateway-secret  (DB_PASSWORD + JWT_SECRET_KEY)
#   k8s/accounting-service/secret.yaml   → ftgo-accounting-service-secret
#   k8s/kitchen-service/secret.yaml      → ftgo-kitchen-service-secret
#   k8s/order-service/secret.yaml        → ftgo-order-service-secret
#   k8s/restaurant-service/secret.yaml   → ftgo-restaurant-service-secret
#   k8s/consumer-service/secret.yaml     → consumer-service-secret
#   k8s/order-history-service/secret.yaml → ftgo-order-history-service-secret
```

### 9.3 — Create AWS Credential Secret (Manual — Cannot Be Committed)

The Universal AI Gateway needs AWS credentials to write audit logs to S3.
These cannot be committed to the repository — create them manually:

```powershell
$AWS_KEY    = $(aws configure get aws_access_key_id)
$AWS_SECRET = $(aws configure get aws_secret_access_key)
$S3_BUCKET  = "ftgo-audit-logs-$ACCOUNT_ID"

# Patch the existing universal-ai-gateway-secret to add AWS credentials
kubectl create secret generic universal-ai-gateway-aws `
    --namespace=ftgo `
    --from-literal=AWS_ACCESS_KEY_ID="$AWS_KEY" `
    --from-literal=AWS_SECRET_ACCESS_KEY="$AWS_SECRET" `
    --from-literal=S3_BUCKET_NAME="$S3_BUCKET"
```

Then add `universal-ai-gateway-aws` as a second `secretRef` in
`k8s/gateway/deployment.yaml` under `envFrom` — or merge the keys
into the existing `universal-ai-gateway-secret` via:

```powershell
# Simpler: patch the existing secret in-place
kubectl patch secret universal-ai-gateway-secret -n ftgo `
    --type=merge `
    -p "{`"data`":{`"AWS_ACCESS_KEY_ID`":`"$([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($AWS_KEY)))`",`"AWS_SECRET_ACCESS_KEY`":`"$([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($AWS_SECRET)))`",`"S3_BUCKET_NAME`":`"$([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($S3_BUCKET)))`"}}"
```

> ⚠️ **Note:** S3 audit logging is optional for the demo. If AWS credentials
> are not added, the gateway falls back gracefully — all API functionality
> works normally, only S3 archival of audit logs is skipped.

### 9.4 — Verify All Secrets Present

```powershell
kubectl get secrets -n ftgo
# Expected: all 7 custom secrets listed (applied via kubectl apply in §11)
```

Expected: 7 custom secrets + Helm-managed secrets listed.

---

## 10. Build and Push Docker Images

> ✅ **Skip this section if images already exist in ECR.**
>
> After any `git push` to the `dev` or `main` branch, GitHub Actions
> automatically builds and pushes all 8 images to ECR. You can verify
> whether images are already available by running:
>
> ```powershell
> aws ecr list-images --repository-name universal-ai-gateway --region $REGION --query 'length(imageIds)'
> # Returns 0 → images missing, run §10. Returns 1 or more → skip to §11.
> ```
>
> **Only run this section if:**
> - This is the very first deployment and CI/CD has never run on this repo, OR
> - You want to force-rebuild all images with local code changes not yet pushed to GitHub

### 10.1 — Authenticate Docker to ECR

```powershell
aws ecr get-login-password --region $REGION | `
    docker login --username AWS --password-stdin $ECR
```

### 10.2 — Build and Push All Services

This takes 15-30 minutes depending on internet speed.
Spring Boot images are 400-600MB each.

```powershell
$SERVICES = @(
    @{name="ftgo-consumer-service";       folder="ftgo-consumer-service"},
    @{name="ftgo-restaurant-service";     folder="ftgo-restaurant-service"},
    @{name="ftgo-accounting-service";     folder="ftgo-accounting-service"},
    @{name="ftgo-kitchen-service";        folder="ftgo-kitchen-service"},
    @{name="ftgo-order-service";          folder="ftgo-order-service"},
    @{name="ftgo-order-history-service";  folder="ftgo-order-history-service"},
    @{name="ftgo-api-gateway";            folder="ftgo-api-gateway"},
    @{name="universal-ai-gateway";        folder="universal-ai-gateway"}
)

foreach ($SVC in $SERVICES) {
    Write-Host "=== Building $($SVC.name) ===" -ForegroundColor Cyan

    docker build -t "$($SVC.name):latest" "./$($SVC.folder)"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Build FAILED: $($SVC.name)" -ForegroundColor Red
        break
    }

    docker tag "$($SVC.name):latest" "$ECR/$($SVC.name):latest"
    docker push "$ECR/$($SVC.name):latest"

    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Push FAILED: $($SVC.name)" -ForegroundColor Red
        break
    }

    Write-Host "✅ $($SVC.name) pushed to ECR" -ForegroundColor Green
}
```

### 10.3 — Verify Images in ECR

```powershell
foreach ($SERVICE in $SERVICES) {
    $COUNT = aws ecr list-images `
        --repository-name $SERVICE.name `
        --region $REGION `
        --query 'length(imageIds)' `
        --output text
    Write-Host "$($SERVICE.name): $COUNT image(s)"
}
```

All services must show at least 1 image before deploying.

---

## 11. Deploy Services

Deploy in this exact order — earlier services have fewer
dependencies. Verify each before proceeding to the next.

### 11.1 — Apply All ConfigMaps

```powershell
$K8S_SERVICES = @(
    "gateway", "order-service", "kitchen-service",
    "restaurant-service", "accounting-service",
    "consumer-service", "order-history-service"
)

foreach ($SVC in $K8S_SERVICES) {
    kubectl apply -f k8s/$SVC/configmap.yaml -n ftgo
    Write-Host "✅ ConfigMap applied: $SVC"
}
```

### 11.2 — Deploy Consumer Service

```powershell
kubectl apply -f k8s/consumer-service/ -n ftgo
kubectl rollout status deployment/ftgo-consumer-service `
    -n ftgo --timeout=300s
```

Expected: `successfully rolled out`

### 11.3 — Deploy Restaurant Service

```powershell
kubectl apply -f k8s/restaurant-service/ -n ftgo
kubectl rollout status deployment/ftgo-restaurant-service `
    -n ftgo --timeout=300s
```

### 11.4 — Deploy Accounting Service

```powershell
kubectl apply -f k8s/accounting-service/ -n ftgo
kubectl rollout status deployment/ftgo-accounting-service `
    -n ftgo --timeout=300s
```

### 11.5 — Deploy Kitchen Service

```powershell
kubectl apply -f k8s/kitchen-service/ -n ftgo
kubectl rollout status deployment/ftgo-kitchen-service `
    -n ftgo --timeout=300s
```

### 11.6 — Deploy Order Service

```powershell
kubectl apply -f k8s/order-service/ -n ftgo
kubectl rollout status deployment/ftgo-order-service `
    -n ftgo --timeout=300s
```

### 11.7 — Deploy Order History Service

```powershell
kubectl apply -f k8s/order-history-service/ -n ftgo
kubectl rollout status deployment/ftgo-order-history-service `
    -n ftgo --timeout=300s
```

### 11.8 — Deploy FTGO API Gateway

```powershell
kubectl apply -f k8s/ftgo-api-gateway/ -n ftgo
kubectl rollout status deployment/ftgo-api-gateway `
    -n ftgo --timeout=300s
```

### 11.9 — Deploy Universal AI Gateway

```powershell
kubectl apply -f k8s/gateway/ -n ftgo
kubectl rollout status deployment/universal-ai-gateway `
    -n ftgo --timeout=300s
```

### 11.10 — Verify All Pods Running

```powershell
kubectl get pods -n ftgo
```

Every pod must show `STATUS=Running` and `READY=1/1`.
Zero pods should be in Pending, CrashLoopBackOff, or Error state.

Expected output (22 pods total):
```
ftgo-accounting-service-xxx      1/1   Running
ftgo-api-gateway-xxx             1/1   Running  (x2)
ftgo-consumer-service-xxx        1/1   Running  (x2)
ftgo-kitchen-service-xxx         1/1   Running  (x2)
ftgo-order-history-service-xxx   1/1   Running  (x2)
ftgo-order-service-xxx           1/1   Running  (x2)
ftgo-postgres-postgresql-0       1/1   Running
ftgo-redis-master-0              1/1   Running
ftgo-redis-replicas-x            1/1   Running  (x3)
ftgo-restaurant-service-xxx      1/1   Running  (x2)
kafka-xxx                        1/1   Running
universal-ai-gateway-xxx         1/1   Running  (x2)
```

---

## 12. Ingress and External Access

### 12.1 — Deploy Ingress

```powershell
kubectl apply -f k8s/ingress/ -n ftgo
```

### 12.2 — Wait for External Address

The AWS Load Balancer Controller creates an Application Load
Balancer. This takes 2-5 minutes.

```powershell
kubectl get ingress -n ftgo -w
# Watch until ADDRESS column shows a hostname like:
# k8s-ftgo-xxxxx.ap-south-1.elb.amazonaws.com
```

Press Ctrl+C once the address appears.

### 12.3 — Save the Load Balancer URL

```powershell
$LB = $(kubectl get ingress -n ftgo `
    -o jsonpath='{.items[0].status.loadBalancer.ingress[0].hostname}')
echo "Load Balancer: $LB"
```

### 12.4 — Wait for DNS Propagation

```powershell
Write-Host "Waiting for load balancer DNS..."
do {
    Start-Sleep -Seconds 15
    $STATUS = try {
        Invoke-WebRequest -Uri "http://$LB/health" `
            -UseBasicParsing -TimeoutSec 5
        "OK"
    } catch { "waiting" }
    Write-Host "Status: $STATUS"
} while ($STATUS -ne "OK")
Write-Host "✅ Load balancer is responding"
```

---

## 13. End-to-End Verification

Run the full order flow to verify the complete system.
Replace `<your-api-key>` with a valid gateway API key.

```powershell
$BASE = "http://$LB"
$KEY = "<your-api-key>"

# 1. Gateway health
Write-Host "=== 1. Gateway Health ===" -ForegroundColor Cyan
Invoke-RestMethod -Uri "$BASE/health" -Method GET

# 2. FTGO gateway health (proxied)
Write-Host "=== 2. FTGO Gateway Health ===" -ForegroundColor Cyan
Invoke-RestMethod -Uri "$BASE/actuator/health" -Method GET

# 3. Create consumer
Write-Host "=== 3. Create Consumer ===" -ForegroundColor Cyan
$CONSUMER = Invoke-RestMethod -Uri "$BASE/api/consumers" `
    -Method POST `
    -ContentType "application/json" `
    -Headers @{Authorization="Bearer $KEY"} `
    -Body '{"name": "EKS Test User"}'
$CONSUMER_ID = $CONSUMER.consumerId
Write-Host "Consumer ID: $CONSUMER_ID"

# 4. Create restaurant
Write-Host "=== 4. Create Restaurant ===" -ForegroundColor Cyan
$RESTAURANT = Invoke-RestMethod -Uri "$BASE/api/restaurants" `
    -Method POST `
    -ContentType "application/json" `
    -Headers @{Authorization="Bearer $KEY"} `
    -Body '{
        "name": "EKS Test Restaurant",
        "menu": {
            "menuItems": [
                {"id": "1", "name": "Burger", "price": "9.99"}
            ]
        }
    }'
$RESTAURANT_ID = $RESTAURANT.id
Write-Host "Restaurant ID: $RESTAURANT_ID"

# 5. Place order (Saga starts here)
Write-Host "=== 5. Place Order ===" -ForegroundColor Cyan
$ORDER = Invoke-RestMethod -Uri "$BASE/api/orders" `
    -Method POST `
    -ContentType "application/json" `
    -Headers @{Authorization="Bearer $KEY"} `
    -Body "{
        `"consumerId`": $CONSUMER_ID,
        `"restaurantId`": $RESTAURANT_ID,
        `"lineItems`": [{`"menuItemId`": `"1`", `"quantity`": 1}]
    }"
$ORDER_ID = $ORDER.orderId
Write-Host "Order ID: $ORDER_ID — State: $($ORDER.state)"
# Must be PENDING — not APPROVED yet

# 6. Poll for Saga completion
Write-Host "=== 6. Polling for Saga Completion ===" -ForegroundColor Cyan
for ($i = 1; $i -le 20; $i++) {
    Start-Sleep -Seconds 3
    $STATUS = Invoke-RestMethod -Uri "$BASE/api/orders/$ORDER_ID" `
        -Headers @{Authorization="Bearer $KEY"}
    Write-Host "Attempt $i: $($STATUS.state)"
    if ($STATUS.state -eq "APPROVED") {
        Write-Host "✅ Saga completed successfully" -ForegroundColor Green
        break
    }
}

# 7. Check CQRS order history
Write-Host "=== 7. Order History (CQRS) ===" -ForegroundColor Cyan
Invoke-RestMethod `
    -Uri "$BASE/api/order-history/orders?consumerId=$CONSUMER_ID" `
    -Headers @{Authorization="Bearer $KEY"}
```

Expected results:
```
1. Gateway health    → {"status": "healthy"}
2. FTGO health       → {"status": "UP"}
3. Consumer created  → consumerId returned
4. Restaurant created → id returned
5. Order placed      → state: PENDING
6. Saga completed    → state: APPROVED (within 60 seconds)
7. History populated → order appears in list
```

---

## 14. Teardown

> ⚠️ Run this immediately after demo. Every hour costs money.

Run the `teardown.py` script:
```powershell
python teardown.py
```

Or manually:
```powershell
# Delete all Kubernetes resources
kubectl delete namespace ftgo

# Destroy EKS cluster (takes 10-15 minutes)
eksctl delete cluster `
    --name $CLUSTER_NAME `
    --region $REGION

# Verify cluster is gone
aws eks list-clusters --region $REGION
# Expected: {"clusters": []}

# Verify ALB is gone
aws elbv2 describe-load-balancers --region $REGION `
    --query 'LoadBalancers[].LoadBalancerName' --output text
# Expected: empty
```

ECR repositories are retained — they contain your images for
instant future redeployment and do not incur significant cost
when idle.

---

## 15. Cost Reference

| Resource | Cost | Notes |
|----------|------|-------|
| EKS control plane | $0.10/hour | Starts immediately on creation |
| t3.medium node × 3 | ~$0.15/hour total | Worker nodes |
| Application Load Balancer | ~$0.025/hour | Created by Ingress |
| EBS volumes (PostgreSQL) | ~$0.005/hour | gp2 storage |
| ECR storage | ~$0.10/GB/month | Minimal when not pushing |
| S3 (audit logs) | Negligible | |
| **Total while running** | **~$0.28/hour** | **~₹23/hour** |

**Estimated demo cost:** ~3-4 hours active = ~₹70-90 total

---

## Quick Reference — Kubernetes DNS Names

All services reachable within the `ftgo` namespace:

```
kafka.ftgo.svc.cluster.local                         :9092
ftgo-postgres-postgresql.ftgo.svc.cluster.local      :5432
ftgo-redis-master.ftgo.svc.cluster.local             :6379
ftgo-consumer-service.ftgo.svc.cluster.local         :80
ftgo-restaurant-service.ftgo.svc.cluster.local       :80
ftgo-accounting-service.ftgo.svc.cluster.local       :80
ftgo-kitchen-service.ftgo.svc.cluster.local          :80
ftgo-order-service.ftgo.svc.cluster.local            :80
ftgo-order-history-service.ftgo.svc.cluster.local    :80
ftgo-api-gateway.ftgo.svc.cluster.local              :80
universal-ai-gateway.ftgo.svc.cluster.local          :80
```

## Quick Reference — Troubleshooting Commands

```powershell
# Check all pods
kubectl get pods -n ftgo

# Check why a pod is failing
kubectl describe pod <pod-name> -n ftgo

# Check pod logs
kubectl logs <pod-name> -n ftgo
kubectl logs <pod-name> -n ftgo --previous

# Check events
kubectl get events -n ftgo --sort-by='.lastTimestamp'

# Check ingress
kubectl get ingress -n ftgo

# Rollback a deployment
kubectl rollout undo deployment/<name> -n ftgo

# Check resource usage
kubectl top pods -n ftgo
```
