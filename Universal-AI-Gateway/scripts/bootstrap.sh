#!/bin/bash
# Universal LLM Gateway - Bootstrap deployment script for Linux/macOS

set -e

echo "================================================="
echo "   Universal LLM Gateway - Deployment Bootstrap  "
echo "================================================="
echo ""

# 1. Check prerequisites
command -v docker >/dev/null 2>&1 || { echo >&2 "Docker is required but it's not installed. Aborting."; exit 1; }

if command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
elif docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
else
    echo >&2 "Docker Compose is required but it's not installed. Aborting."
    exit 1
fi

# 2. Setup Environment Variables
if [ ! -f ".env" ]; then
    echo "Creating .env file from .env.example..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
    else
        echo "Error: .env.example not found! Providing empty fallback..."
        touch .env
    fi
else
    echo "Found existing .env file. Skipping creation."
fi

# Interactive API Key prompt
read -p "Would you like to configure API keys now? [y/N]: " configure_keys
if [[ "$configure_keys" =~ ^[Yy]$ ]]; then
    read -p "Enter OpenAI API Key (leave blank to skip): " openai_key
    if [ ! -z "$openai_key" ]; then
        if grep -q "^OPENAI_API_KEY=" .env; then
            # Cross-platform sed for both GNU (Linux) and BSD (macOS)
            sed -i.bak "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=$openai_key|" .env && rm -f .env.bak
        else
            echo "OPENAI_API_KEY=$openai_key" >> .env
        fi
    fi
    
    read -p "Enter Anthropic API Key (leave blank to skip): " anthropic_key
    if [ ! -z "$anthropic_key" ]; then
        if grep -q "^ANTHROPIC_API_KEY=" .env; then
            sed -i.bak "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$anthropic_key|" .env && rm -f .env.bak
        else
            echo "ANTHROPIC_API_KEY=$anthropic_key" >> .env
        fi
    fi
    echo "API keys recorded in .env"
fi

# 3. Start services
echo ""
echo "Starting Docker containers in detached mode..."
$DOCKER_COMPOSE up -d --build

# 4. Wait for database/services to initialize
echo "Waiting for PostgreSQL and Gateway to initialize (10 seconds)..."
sleep 10

# 5. Run Alembic Migrations
echo "Applying database metadata migrations via Alembic..."
if $DOCKER_COMPOSE exec -T gateway alembic upgrade head; then
    echo "Migrations applied successfully."
else
    echo "Warning: Migration command failed or DB is not yet accepting connections. Please check logs with '$DOCKER_COMPOSE logs gateway'."
fi

echo ""
echo "================================================="
echo "Deployment Complete! 🚀"
echo "Gateway URL:   http://localhost:8000"
echo "API Docs:      http://localhost:8000/docs"
echo "Health Check:  http://localhost:8000/health"
echo "Grafana:       Import 'grafana-dashboard.json' into your deployment"
echo "================================================="
