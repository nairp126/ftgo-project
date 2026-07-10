# Generate OpenAPI SDKs locally using Docker.
$ErrorActionPreference = "Stop"

# 1. Export openapi.json
Write-Host "Exporting openapi.json..." -ForegroundColor Green
python scripts/export_openapi.py

# 2. Create SDK directories
New-Item -ItemType Directory -Force -Path sdks/python
New-Item -ItemType Directory -Force -Path sdks/typescript

# 3. Generate Python SDK
Write-Host "Generating Python SDK..." -ForegroundColor Green
docker run --rm -v "${PWD}:/local" openapitools/openapi-generator-cli generate `
    -i /local/openapi.json `
    -g python `
    -o /local/sdks/python `
    --additional-properties=packageName=universal_ai_gateway

# 4. Generate TypeScript SDK
Write-Host "Generating TypeScript SDK..." -ForegroundColor Green
docker run --rm -v "${PWD}:/local" openapitools/openapi-generator-cli generate `
    -i /local/openapi.json `
    -g typescript-axios `
    -o /local/sdks/typescript

Write-Host "SDK generation complete!" -ForegroundColor Green
