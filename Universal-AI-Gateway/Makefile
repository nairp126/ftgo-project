.PHONY: test lint openapi helm-lint docker-build run

PYTHON = python
PYTEST = pytest
RUFF = ruff
DOCKER = docker

test:
	$(PYTEST)

lint:
	$(RUFF) check .

openapi:
	$(PYTHON) scripts/export_openapi.py

helm-lint:
	helm lint charts/gateway

docker-build:
	$(DOCKER) build -t universal-ai-gateway:latest .

run:
	$(PYTHON) run.py

# SDK Generation (requires openapi-generator-cli)
sdk-py: openapi
	$(DOCKER) run --rm -v "${PWD}:/local" openapitools/openapi-generator-cli generate \
		-i /local/openapi.json \
		-g python \
		-o /local/sdk/python

sdk-ts: openapi
	$(DOCKER) run --rm -v "${PWD}:/local" openapitools/openapi-generator-cli generate \
		-i /local/openapi.json \
		-g typescript-axios \
		-o /local/sdk/typescript
