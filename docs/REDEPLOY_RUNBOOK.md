# FTGO Fresh EKS Redeploy Runbook

> Run this top-to-bottom after `python teardown.py` + `eksctl create cluster`.  
> All commands are idempotent — safe to re-run.  
> Expected time: ~45 minutes.

---

## Prerequisites

```powershell
aws sts get-caller-identity          # confirm correct AWS account
eksctl version                       # >= 0.170
kubectl version --client             # >= 1.28
helm version                         # >= 3.12
```

---

## Step 1 — Create EKS Cluster

```bash
eksctl create cluster \
  --name ftgo-eks-cluster \
  --region ap-south-1 \
  --nodegroup-name standard-workers \
  --node-type t3.medium \
  --nodes 3 --nodes-min 2 --nodes-max 4 \
  --managed

kubectl get nodes
# Expected: 3 nodes STATUS=Ready
```

---

## Step 2 — Install AWS Load Balancer Controller

```bash
# 2a. Download & create IAM policy
curl -o alb-policy.json \
  https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/main/docs/install/iam_policy.json

aws iam create-policy \
  --policy-name AWSLoadBalancerControllerIAMPolicy \
  --policy-document file://alb-policy.json

# 2b. Create IAM service account (links new OIDC provider to role)
eksctl create iamserviceaccount \
  --cluster=ftgo-eks-cluster \
  --namespace=kube-system \
  --name=aws-load-balancer-controller \
  --role-name AmazonEKSLoadBalancerControllerRole \
  --attach-policy-arn=arn:aws:iam::120569617989:policy/AWSLoadBalancerControllerIAMPolicy \
  --approve

# 2c. Install via Helm
helm repo add eks https://aws.github.io/eks-charts
helm repo update
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=ftgo-eks-cluster \
  --set serviceAccount.create=false \
  --set serviceAccount.name=aws-load-balancer-controller

kubectl get deployment -n kube-system aws-load-balancer-controller
# Expected: READY 1/1
```

---

## Step 3 — Create Namespace

```bash
kubectl create namespace ftgo
kubectl config set-context --current --namespace=ftgo
```

---

## Step 4 — Install PostgreSQL & Redis via Helm

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# PostgreSQL — shared by all microservices
helm install ftgo-postgres bitnami/postgresql \
  --namespace ftgo \
  --set auth.postgresPassword=mysecretpassword \
  --set auth.database=postgres \
  --set primary.persistence.size=2Gi

# Redis — used by Universal AI Gateway for caching
helm install ftgo-redis bitnami/redis \
  --namespace ftgo \
  --set auth.enabled=false \
  --set replica.replicaCount=2

# Wait for both to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=postgresql -n ftgo --timeout=120s
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=redis -n ftgo --timeout=120s
```

---

## Step 5 — Apply All Kubernetes Manifests

```bash
# 5a. Secrets and ConfigMaps first
for SERVICE in gateway order-service kitchen-service restaurant-service \
               accounting-service consumer-service order-history-service; do
  kubectl apply -f k8s/$SERVICE/ -n ftgo 2>/dev/null || true
done

# 5b. Kafka
kubectl apply -f k8s/kafka/ -n ftgo
kubectl wait --for=condition=ready pod -l app=kafka -n ftgo --timeout=180s

# 5c. Domain services (in dependency order)
for SERVICE in consumer-service restaurant-service accounting-service \
               kitchen-service order-service order-history-service; do
  echo "=== Deploying $SERVICE ==="
  kubectl apply -f k8s/$SERVICE/ -n ftgo
  kubectl rollout status deployment/ftgo-$SERVICE -n ftgo --timeout=300s
done

# 5d. Gateways
kubectl apply -f k8s/ftgo-api-gateway/ -n ftgo
kubectl rollout status deployment/ftgo-api-gateway -n ftgo --timeout=300s

kubectl apply -f k8s/gateway/ -n ftgo
kubectl rollout status deployment/universal-ai-gateway -n ftgo --timeout=300s

# 5e. Ingress
kubectl apply -f k8s/ingress/ -n ftgo
```

---

## Step 6 — Get New ALB URL & Update Demo Scripts

```bash
# Wait 2-3 minutes for ALB to provision, then:
kubectl get ingress ftgo-ingress -n ftgo \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

Update the LB variable in **both** demo scripts with the new hostname:

```python
# demo-commands.py  — line 8
LB = "http://<NEW-ALB-HOSTNAME>.ap-south-1.elb.amazonaws.com"

# demo-day-check.py — line 8
LB = "http://<NEW-ALB-HOSTNAME>.ap-south-1.elb.amazonaws.com"
```

---

## Step 7 — Verify Everything

```bash
# All pods running?
kubectl get pods -n ftgo
# Expected: 22 pods, all Running

# Run pre-check
python demo-day-check.py
# Expected: 14/14 PASS — ALL GREEN

# Run full E2E
python demo-commands.py
# Expected: All 7 steps PASS
```

---

## CI/CD After Fresh Deploy

GitHub Actions pipelines require **zero changes** after fresh deploy:

- `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` live in GitHub Secrets — unchanged
- ECR repository URIs are unchanged (`120569617989.dkr.ecr.ap-south-1.amazonaws.com/*`)
- On the next `git push` to `dev` or `main`, all 7 workflows rebuild and push to ECR automatically
- Deployments use `imagePullPolicy: Always` with `:latest` tag — pods always pull fresh ECR image

To trigger a manual redeploy of all services after a fresh cluster, push an empty commit:

```bash
git commit --allow-empty -m "chore: trigger CI redeploy on fresh cluster"
git push origin dev
```

---

## What Resets on Fresh Deploy (Expected)

| What | Resets? | Impact |
|------|---------|--------|
| PostgreSQL data (consumers, orders, restaurants) | YES — empty DB | Create fresh demo data at demo time |
| Redis cache | YES — empty | No impact (cache warms automatically) |
| ALB hostname | YES — new URL | Update demo scripts (Step 6) |
| ECR images | NO — persist | Zero rebuild needed |
| K8s secrets / configmaps | NO — in repo | `kubectl apply` reapplies them |
| GitHub Actions workflows | NO — in repo | Still green |
| AWS IAM roles/policy for LBC | YES — deleted by teardown | Recreated in Step 2 |

---

*FTGO Microservices Platform — Fresh Deploy Runbook*  
*Account: `120569617989` | Region: `ap-south-1` | Cluster: `ftgo-eks-cluster`*
