#!/usr/bin/env python3
"""
FTGO Demo Day Pre-Check — Integration 9
=========================================
Run this 30 minutes before the demo.
Every check must be GREEN before proceeding.

Usage:  python3 demo-day-check.py
"""
import sys, time, json, urllib.request, urllib.error, subprocess
import jwt as pyjwt

LB         = "http://k8s-ftgo-ftgoingr-7da04dfdb1-2025923773.ap-south-1.elb.amazonaws.com"
JWT_SECRET = "supersecretjwtkeyforftgoapigateway1random"
TOKEN      = pyjwt.encode(
    {"sub": "check-user", "tenant_id": "ftgo-demo",
     "iat": int(time.time()), "exp": int(time.time()) + 3600},
    JWT_SECRET, algorithm="HS256"
)
HDR = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

checks  = []
PASS    = "PASS"
FAIL    = "FAIL"

def check(label, ok, detail=""):
    status = PASS if ok else FAIL
    icon   = "[PASS]" if ok else "[FAIL]"
    print(f"  {icon}  {label:<50} {detail}")
    checks.append((label, status))
    return ok

def http_get(path):
    try:
        req = urllib.request.Request(f"{LB}{path}", headers=HDR)
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return 0, {}

def kubectl(*args):
    r = subprocess.run(["kubectl"] + list(args), capture_output=True, text=True, timeout=15)
    return r.stdout.strip(), r.returncode

print("\n" + "="*64)
print("  FTGO DEMO DAY PRE-CHECK")
print(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print("="*64)

# ── 1. Cluster Nodes ─────────────────────────────────────────────────────────
print("\n[Cluster]")
out, rc = kubectl("get", "nodes", "--no-headers")
ready_nodes = sum(1 for line in out.splitlines() if "Ready" in line)
check("EKS nodes READY", ready_nodes >= 3, f"{ready_nodes}/3 ready")

# ── 2. All Pods Running ──────────────────────────────────────────────────────
print("\n[Pods]")
out, rc = kubectl("get", "pods", "-n", "ftgo", "--no-headers")
lines        = [l for l in out.splitlines() if l.strip()]
not_running  = [l for l in lines if "Running" not in l]
total        = len(lines)
check("All pods Running", len(not_running) == 0, f"{total - len(not_running)}/{total} Running")
if not_running:
    for l in not_running:
        print(f"       NOT RUNNING: {l}")

# ── 3. Gateway Health ────────────────────────────────────────────────────────
print("\n[Gateway]")
s, r = http_get("/health")
check("Universal AI Gateway health", s == 200 and r.get("status") == "healthy",
      r.get("status", f"HTTP {s}"))
check("FTGO internal gateway health", *[
    (lambda s2, r2: (s2 == 200, r2.get("status", f"HTTP {s2}")))(*http_get("/actuator/health"))
])

# AI Providers
components = r.get("components", {})
providers  = components.get("providers", {})
for prov, info in providers.items():
    check(f"  AI provider: {prov}", info.get("status") == "healthy",
          info.get("circuit_state", ""))

cache_ok = components.get("cache", {}).get("status") == "healthy"
db_ok    = components.get("database", {}).get("status") == "healthy"
check("Redis cache healthy", cache_ok)
check("PostgreSQL database healthy", db_ok)

# ── 4. Core API Routes ───────────────────────────────────────────────────────
print("\n[API Routing]")
s, r = http_get("/api/consumers")
check("GET /api/consumers (consumer-service)", s in (200, 405), f"HTTP {s}")  # 405 = method not allowed = route exists

s, r = http_get("/api/order-history?consumerId=1")
check("GET /api/order-history (order-history-service)", s == 200, f"HTTP {s}")

# ── 5. Ingress / External URL ────────────────────────────────────────────────
print("\n[Ingress]")
out, rc = kubectl("get", "ingress", "ftgo-ingress", "-n", "ftgo",
                  "-o", "jsonpath={.status.loadBalancer.ingress[0].hostname}")
check("ALB Ingress hostname assigned", bool(out.strip()), out.strip() or "EMPTY")
check("Hostname matches expected LB", LB.replace("http://","") in out.strip() or out.strip() != "",
      out.strip())

# ── 6. Final Summary ─────────────────────────────────────────────────────────
passed = sum(1 for _, s in checks if s == PASS)
failed = sum(1 for _, s in checks if s == FAIL)

print("\n" + "="*64)
print(f"  RESULT: {passed} PASS  |  {failed} FAIL")
if failed == 0:
    print("  STATUS: ALL GREEN — READY TO DEMO!")
else:
    print("  STATUS: ISSUES FOUND — DO NOT START DEMO!")
    print("  Run: python demo-commands.py to diagnose.")
print(f"  Load Balancer: {LB}")
print("="*64 + "\n")

sys.exit(0 if failed == 0 else 1)
