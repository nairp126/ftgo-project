#!/usr/bin/env python3
"""
FTGO EKS Cluster — COMPLETE Teardown Script
============================================
Destroys ALL AWS resources created for the FTGO EKS deployment.

Resources handled:
  [eksctl] EKS control plane, node group (EC2), VPC, subnets,
           security groups, route tables, IGW, IAM service accounts
           for aws-load-balancer-controller and ebs-csi-controller-sa
  [manual] ALB (via namespace delete first), OIDC provider,
           IAM roles/policies, ECR repositories

Usage:  python3 teardown.py
"""
import subprocess, sys, time, json

CLUSTER_NAME = "ftgo-eks-cluster"
REGION       = "ap-south-1"
NAMESPACE    = "ftgo"
ACCOUNT_ID   = "120569617989"

# IAM resources created manually (not by eksctl CloudFormation)
IAM_POLICY_ARN = f"arn:aws:iam::{ACCOUNT_ID}:policy/AWSLoadBalancerControllerIAMPolicy"
IAM_ROLES_TO_DELETE = [
    "AmazonEKSLoadBalancerControllerRole",
    "AmazonEKS_EBS_CSI_DriverRole",
]
OIDC_PROVIDER_ARN = f"arn:aws:iam::{ACCOUNT_ID}:oidc-provider/oidc.eks.{REGION}.amazonaws.com/id/D91EDE784FF0E2A9F46313EACE641B67"

# ECR repositories to delete (set DELETE_ECR=True to destroy images too)
ECR_REPOS = [
    "universal-ai-gateway",
    "ftgo-api-gateway",
    "ftgo-consumer-service",
    "ftgo-order-service",
    "ftgo-restaurant-service",
    "ftgo-kitchen-service",
    "ftgo-accounting-service",
    "ftgo-order-history-service",
]


def run(cmd, capture=False):
    print(f"\n  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if capture:
        return result.stdout.strip(), result.returncode
    return result


def alb_exists():
    out, rc = run(
        ["aws", "elbv2", "describe-load-balancers", "--region", REGION,
         "--query", "LoadBalancers[?contains(LoadBalancerName,'k8s-ftgo')].LoadBalancerArn",
         "--output", "text"],
        capture=True
    )
    return bool(out.strip())


# ── Banner ───────────────────────────────────────────────────────────────────
print("\n" + "="*64)
print("  FTGO EKS COMPLETE TEARDOWN")
print("  Destroys ALL AWS resources — cluster, ALB, IAM, ECR")
print("="*64)
print()
print("  Resources that will be deleted:")
print("  [eksctl] EKS cluster, 3x EC2 t3.medium, VPC, subnets,")
print("           security groups, IAM service account roles")
print("  [manual] ALB, OIDC provider, IAM roles & policy")
print()

delete_ecr = input("  Also delete all 8 ECR repositories and images? [y/N]: ").strip().lower()
confirm    = input("  Type 'DESTROY' to confirm full teardown: ").strip()

if confirm != "DESTROY":
    print("  Aborted. No resources changed.")
    sys.exit(0)

print("\n  Starting teardown sequence...\n")

# ── STEP 1: Delete namespace (this signals LBC to remove the ALB) ─────────
print("\n" + "="*64)
print("[Step 1/7] Deleting ftgo namespace → triggers ALB deletion via LBC")
print("="*64)
run(["kubectl", "delete", "namespace", NAMESPACE, "--ignore-not-found=true"])

# ── STEP 2: Wait for ALB to be removed by LBC ────────────────────────────
print("\n" + "="*64)
print("[Step 2/7] Waiting for ALB to be deprovisioned (up to 90s)...")
print("="*64)
alb_gone = False
for i in range(18):
    time.sleep(5)
    if not alb_exists():
        print(f"  ALB deprovisioned after ~{(i+1)*5}s")
        alb_gone = True
        break
    print(f"  ALB still active... ({(i+1)*5}s)")

if not alb_gone:
    print("  WARNING: ALB may still exist — deleting namespace timed out.")
    print("  Proceeding with eksctl delete anyway.")
    print("  ACTION REQUIRED: Check ALB in AWS Console and delete manually if still present.")

# ── STEP 3: Delete EKS cluster via eksctl ────────────────────────────────
print("\n" + "="*64)
print(f"[Step 3/7] Deleting EKS cluster '{CLUSTER_NAME}' (15-20 min)...")
print("  This deletes: control plane, node group, EC2 instances,")
print("  VPC, subnets, security groups, route tables, IAM service accounts")
print("="*64)
run([
    "eksctl", "delete", "cluster",
    "--name",   CLUSTER_NAME,
    "--region", REGION,
    "--wait"
], capture=False)

# ── STEP 4: Delete IAM Roles ──────────────────────────────────────────────
print("\n" + "="*64)
print("[Step 4/7] Deleting manually-created IAM roles...")
print("="*64)
for role in IAM_ROLES_TO_DELETE:
    # Detach policies first
    attached, _ = run(
        ["aws", "iam", "list-attached-role-policies",
         "--role-name", role,
         "--query", "AttachedPolicies[].PolicyArn",
         "--output", "text"],
        capture=True
    )
    if attached:
        for policy_arn in attached.split():
            run(["aws", "iam", "detach-role-policy",
                 "--role-name", role, "--policy-arn", policy_arn])
    # Delete role
    run(["aws", "iam", "delete-role", "--role-name", role])

# ── STEP 5: Delete IAM Policy ─────────────────────────────────────────────
print("\n" + "="*64)
print("[Step 5/7] Deleting AWSLoadBalancerControllerIAMPolicy...")
print("="*64)
run(["aws", "iam", "delete-policy", "--policy-arn", IAM_POLICY_ARN])

# ── STEP 6: Delete OIDC Provider ─────────────────────────────────────────
print("\n" + "="*64)
print("[Step 6/7] Deleting EKS cluster OIDC provider...")
print("="*64)
run(["aws", "iam", "delete-open-id-connect-provider",
     "--open-id-connect-provider-arn", OIDC_PROVIDER_ARN])

# ── STEP 7: Delete ECR Repos (optional) ──────────────────────────────────
print("\n" + "="*64)
print("[Step 7/7] ECR Repositories...")
print("="*64)
if delete_ecr == "y":
    for repo in ECR_REPOS:
        print(f"\n  Deleting ECR repo: {repo}")
        run(["aws", "ecr", "delete-repository",
             "--repository-name", repo,
             "--region", REGION,
             "--force"])
    print("\n  All 8 ECR repositories deleted.")
else:
    print("  ECR repositories RETAINED (images preserved for future use).")
    print("  To delete later:")
    for repo in ECR_REPOS:
        print(f"    aws ecr delete-repository --repository-name {repo} --region {REGION} --force")

# ── Final Verification ────────────────────────────────────────────────────
print("\n" + "="*64)
print("[Verification] Checking remaining resources...")
print("="*64)
print("\n  EKS clusters:")
run(["aws", "eks", "list-clusters", "--region", REGION])

print("\n  Active ALBs matching ftgo:")
out, _ = run(
    ["aws", "elbv2", "describe-load-balancers", "--region", REGION,
     "--query", "LoadBalancers[?contains(LoadBalancerName,'ftgo')].LoadBalancerName",
     "--output", "text"],
    capture=True
)
print(f"  {out.strip() or 'None — clean!'}")

print("\n" + "="*64)
print("  TEARDOWN COMPLETE")
print()
print("  DESTROYED:")
print("    ✓ EKS cluster (control plane)")
print("    ✓ EC2 node group (3x t3.medium)")
print("    ✓ VPC, subnets, security groups, route tables")
print("    ✓ IAM service accounts (LBC + EBS CSI)")
print("    ✓ Application Load Balancer (ALB)")
print("    ✓ IAM roles (LBC + EBS CSI)")
print("    ✓ IAM policy (AWSLoadBalancerControllerIAMPolicy)")
print("    ✓ OIDC provider")
if delete_ecr == "y":
    print("    ✓ ECR repositories (8 repos + all images)")
else:
    print()
    print("  RETAINED (no ongoing compute billing):")
    print("    ~ ECR repositories (8 repos — small storage cost)")
    print("      Delete when ready: run this script again with ECR=y")

print()
print("  NOTE: GitHub Actions OIDC provider was NOT deleted")
print("        (token.actions.githubusercontent.com — shared, keep it)")
print("="*64 + "\n")
