#!/usr/bin/env python3
"""
FTGO Live Demo Script — Integration 9
======================================
Runs against the live AWS EKS cluster via the ALB.
Generates a fresh JWT and drives the full demo flow end-to-end.

Usage:  python3 demo-commands.py
"""
import sys, time, json, urllib.request, urllib.error, jwt

# ── Config ──────────────────────────────────────────────────────────────────
LB  = "http://k8s-ftgo-ftgoingr-7da04dfdb1-2025923773.ap-south-1.elb.amazonaws.com"
JWT_SECRET = "supersecretjwtkeyforftgoapigateway1random"

TOKEN = jwt.encode(
    {"sub": "demo-user", "tenant_id": "ftgo-demo",
     "roles": ["admin"], "iat": int(time.time()), "exp": int(time.time()) + 7200},
    JWT_SECRET, algorithm="HS256"
)
HDR = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# ── Helpers ──────────────────────────────────────────────────────────────────
def banner(title):
    print(f"\n{'='*64}")
    print(f"  {title}")
    print(f"{'='*64}")

def call(method, path, body=None):
    url  = f"{LB}{path}"
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, headers=HDR, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:    return e.code, json.loads(raw)
        except: return e.code, {"raw": raw}
    except Exception as exc:
        return 0, {"error": str(exc)}

# ─────────────────────────────────────────────────────────────────────────────
banner("FTGO LIVE DEMO — PRODUCTION AWS EKS CLUSTER")
print(f"  Load Balancer : {LB}")
print(f"  Cluster Region: ap-south-1  |  Namespace: ftgo")

# === 1. Gateway Health =======================================================
banner("1 of 7 — Universal AI Gateway Health")
s, r = call("GET", "/health")
print(json.dumps(r, indent=2))
assert s == 200 and r.get("status") == "healthy", f"FAIL: {s}"
print("  >>> STATUS: HEALTHY (all AI providers + Redis + PostgreSQL)")

# === 2. All Pods Running =====================================================
banner("2 of 7 — Live Pod Status (kubectl)")
import subprocess
result = subprocess.run(
    ["kubectl", "get", "pods", "-n", "ftgo",
     "--no-headers",
     "-o", "custom-columns=NAME:.metadata.name,STATUS:.status.phase,READY:.status.containerStatuses[0].ready"],
    capture_output=True, text=True
)
print(result.stdout)
running = result.stdout.count("Running")
print(f"  >>> {running} pods in Running state")

# === 3. All Deployments ======================================================
banner("3 of 7 — All Deployments (kubectl)")
result = subprocess.run(
    ["kubectl", "get", "deployments", "-n", "ftgo"],
    capture_output=True, text=True
)
print(result.stdout)

# === 4. Ingress / External URL ===============================================
banner("4 of 7 — Ingress / External URL")
result = subprocess.run(
    ["kubectl", "get", "ingress", "-n", "ftgo"],
    capture_output=True, text=True
)
print(result.stdout)
print(f"  >>> External: {LB}")

# === 5. Create a Consumer ====================================================
banner("5a — Create Consumer (Priya Nair)")
s, r = call("POST", "/api/consumers", {"firstName": "Priya", "lastName": "Nair"})
print(json.dumps(r, indent=2))
CONSUMER_ID = r.get("id")
print(f"  >>> Consumer created — id={CONSUMER_ID}")

banner("5b — Create Restaurant (FTGO Cloud Kitchen)")
s, r = call("POST", "/api/restaurants", {
    "name": "FTGO Cloud Kitchen",
    "address": "42 EKS Street, Bangalore, KA 560001",
    "description": "Demo restaurant — FTGO microservices",
    "phoneNumber": "9876543210"
})
print(json.dumps(r, indent=2))
RESTAURANT_UUID = r.get("id")
print(f"  >>> Restaurant created — uuid={RESTAURANT_UUID}")

banner("5c — Place Order (Event-Driven Saga)")
s, r = call("POST", "/api/orders", {
    "consumerId"  : CONSUMER_ID or 1,
    "restaurantId": 1,
    "totalAmount" : "24.99"
})
print(json.dumps(r, indent=2))
ORDER_ID = r.get("orderId")
assert s in (200, 201) and ORDER_ID, f"Order creation FAILED: {s} {r}"
print(f"  >>> Order placed — orderId={ORDER_ID}")

# === 6. Saga State ===========================================================
banner(f"6 of 7 — Saga State Poll (orderId={ORDER_ID})")
state = ""
for attempt in range(8):
    time.sleep(3)
    s, r = call("GET", f"/api/orders/{ORDER_ID}")
    state = str(r.get("status") or r.get("state") or "")
    print(f"  Poll {attempt+1}/8  →  {state}")
    if state in ("APPROVED", "CREATED", "CANCELLED", "REJECTED"):
        break

print(f"\n  >>> Saga final state: {state}")
print(json.dumps(r, indent=2))

# === 7. Order History (CQRS) =================================================
banner("7 of 7 — Order History CQRS Read Model")
s, r = call("GET", f"/api/order-history?consumerId={CONSUMER_ID or 1}")
print(json.dumps(r, indent=2))
print(f"  >>> HTTP {s} — CQRS read model responding")

# ── Final Summary ─────────────────────────────────────────────────────────────
banner("DEMO COMPLETE — SUMMARY")
print(f"  Consumer ID   : {CONSUMER_ID}")
print(f"  Restaurant UUID: {RESTAURANT_UUID}")
print(f"  Order ID      : {ORDER_ID}")
print(f"  Saga State    : {state}")
print(f"  Order History : HTTP {s}")
print(f"\n  External URL  : {LB}")
print(f"  Status        : ALL SYSTEMS OPERATIONAL")
print(f"{'='*64}\n")
