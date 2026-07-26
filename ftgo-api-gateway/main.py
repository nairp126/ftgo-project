import httpx
from fastapi import FastAPI, Request, Response

app = FastAPI(title="FTGO Internal API Gateway")

# Service routing map: maps service_name prefix to exact upstream base URL
SERVICE_MAP = {
    "orders": "http://ftgo-order-service:8080/orders",
    "consumers": "http://ftgo-consumer-service:8080/consumers",
    "kitchen": "http://ftgo-kitchen-service:8080/api/kitchen",
    "restaurants": "http://ftgo-restaurant-service:8080/api/restaurants",
    "accounting": "http://ftgo-accounting-service:8080/accounting",
    "order-history": "http://ftgo-order-history-service:8080/orders",
}

@app.get("/actuator/health")
async def actuator_health():
    return {"status": "UP"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.api_route("/{service_name}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.api_route("/{service_name}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy_request(service_name: str, request: Request, path: str = ""):
    if service_name not in SERVICE_MAP:
        return Response(content=f'{{"error": "Unknown service: {service_name}"}}', status_code=404, media_type="application/json")
    
    target_base = SERVICE_MAP[service_name]
    target_url = f"{target_base}/{path}" if path else target_base
    
    headers = dict(request.headers)
    headers.pop("host", None)
    body = await request.body()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=dict(request.query_params)
            )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=dict(resp.headers)
            )
        except Exception as e:
            return Response(
                content=f'{{"error": "Upstream service error", "details": "{str(e)}"}}',
                status_code=503,
                media_type="application/json"
            )
