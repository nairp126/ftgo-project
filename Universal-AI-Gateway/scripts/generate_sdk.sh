#!/bin/bash
# Generate OpenAPI SDKs locally using Docker.
set -e

# 1. Export openapi.json
echo "Exporting openapi.json..."
python scripts/export_openapi.py

# 2. Create SDK directories
mkdir -p sdks/python
mkdir -p sdks/typescript

# 3. Generate Python SDK
echo "Generating Python SDK..."
docker run --rm -v "${PWD}:/local" openapitools/openapi-generator-cli generate \
    -i /local/openapi.json \
    -g python \
    -o /local/sdks/python \
    --additional-properties=packageName=universal_ai_gateway

# 4. Generate TypeScript SDK
echo "Generating TypeScript SDK..."
docker run --rm -v "${PWD}:/local" openapitools/openapi-generator-cli generate \
    -i /local/openapi.json \
    -g typescript-axios \
    -o /local/sdks/typescript

echo "SDK generation complete!"
