#!/usr/bin/env python3
"""
FTGO EKS Cluster Teardown — Integration 9
==========================================
Run this IMMEDIATELY after the demo ends.
This will delete all AWS resources and stop billing.

Usage:  python3 teardown.py
"""
import subprocess, sys, time

CLUSTER_NAME = "ftgo-eks-cluster"
REGION       = "ap-south-1"
NAMESPACE    = "ftgo"

def run(cmd, check=True):
    print(f"\n  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False, text=True)
    if check and result.returncode != 0:
        print(f"  WARNING: Command exited {result.returncode}")
    return result

print("\n" + "="*64)
print("  FTGO EKS CLUSTER TEARDOWN")
print("  This will delete ALL AWS resources and stop billing.")
print("="*64)
print()

confirm = input("  Type 'DESTROY' to confirm teardown: ").strip()
if confirm != "DESTROY":
    print("  Aborted. Cluster left running.")
    sys.exit(0)

print("\n  Starting teardown sequence...\n")

# Step 1: Delete the FTGO namespace (removes all pods, services, configmaps, secrets)
print("\n[Step 1] Deleting ftgo namespace (all microservices, configmaps, secrets)...")
run(["kubectl", "delete", "namespace", NAMESPACE, "--ignore-not-found=true"])

# Step 2: Wait for namespace termination
print("\n[Step 2] Waiting for namespace to terminate (up to 60s)...")
for i in range(12):
    result = subprocess.run(
        ["kubectl", "get", "namespace", NAMESPACE],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("  Namespace terminated.")
        break
    print(f"  Still terminating... ({(i+1)*5}s)")
    time.sleep(5)

# Step 3: Delete EKS cluster (this will also remove the ALB/ingress)
print(f"\n[Step 3] Deleting EKS cluster '{CLUSTER_NAME}' in {REGION}...")
print("  (This may take 15-20 minutes — safe to leave running)")
run([
    "eksctl", "delete", "cluster",
    "--name",   CLUSTER_NAME,
    "--region", REGION,
    "--wait"
], check=False)

# Step 4: Verify
print("\n[Step 4] Verifying cluster deletion...")
run(["aws", "eks", "list-clusters", "--region", REGION])

print("\n" + "="*64)
print("  TEARDOWN COMPLETE")
print("  All EKS resources deleted — billing stopped.")
print("  ECR images are still retained in:")
print("    120569617989.dkr.ecr.ap-south-1.amazonaws.com/")
print("  Delete ECR repos manually if no longer needed.")
print("="*64 + "\n")
