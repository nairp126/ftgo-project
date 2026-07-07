<#
.SYNOPSIS
Universal LLM Gateway - Bootstrap deployment script for Windows
#>

$ErrorActionPreference = "Stop"

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "   Universal LLM Gateway - Deployment Bootstrap  " -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check prerequisites
if (-not (Get-Command "docker" -ErrorAction SilentlyContinue)) {
    Write-Error "Docker is required but it's not installed. Aborting."
    exit 1
}

$DockerComposeCmd = ""
if (Get-Command "docker-compose" -ErrorAction SilentlyContinue) {
    $DockerComposeCmd = "docker-compose"
} elseif (docker compose version 2>$null) {
    $DockerComposeCmd = "docker compose"
} else {
    Write-Error "Docker Compose is required but it's not installed. Aborting."
    exit 1
}

# 2. Setup Environment Variables
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env file from .env.example..."
    if (Test-Path ".env.example") {
        Copy-Item -Path ".env.example" -Destination ".env"
    } else {
        Write-Warning "Error: .env.example not found! Creating an empty .env file..."
        New-Item -Path ".env" -ItemType File | Out-Null
    }
} else {
    Write-Host "Found existing .env file. Skipping creation."
}

# Interactive API Key prompt
$configureKeys = Read-Host "Would you like to configure API keys now? (y/n)"
if ($configureKeys -match '^[Yy]$') {
    $envContent = Get-Content ".env" -ErrorAction SilentlyContinue
    if ($null -eq $envContent) { $envContent = @() }
    
    $openaiKey = Read-Host "Enter OpenAI API Key (leave blank to skip)"
    if (-not [string]::IsNullOrWhiteSpace($openaiKey)) {
        if ($envContent -match "^OPENAI_API_KEY=") {
            $envContent = $envContent -replace "^OPENAI_API_KEY=.*", "OPENAI_API_KEY=$openaiKey"
        } else {
            $envContent += "OPENAI_API_KEY=$openaiKey"
        }
    }
    
    $anthropicKey = Read-Host "Enter Anthropic API Key (leave blank to skip)"
    if (-not [string]::IsNullOrWhiteSpace($anthropicKey)) {
        if ($envContent -match "^ANTHROPIC_API_KEY=") {
            $envContent = $envContent -replace "^ANTHROPIC_API_KEY=.*", "ANTHROPIC_API_KEY=$anthropicKey"
        } else {
            $envContent += "ANTHROPIC_API_KEY=$anthropicKey"
        }
    }
    
    $envContent | Set-Content ".env" -Encoding UTF8
    Write-Host "API keys recorded in .env" -ForegroundColor Green
}

# 3. Start services
Write-Host "`nStarting Docker containers in detached mode..."
if ($DockerComposeCmd -eq "docker-compose") {
    docker-compose up -d --build
} else {
    docker compose up -d --build
}

# 4. Wait for database/services to initialize
Write-Host "Waiting for PostgreSQL and Gateway to initialize (10 seconds)..."
Start-Sleep -Seconds 10

# 5. Run migrations
Write-Host "Applying database metadata migrations via Alembic..."
try {
    if ($DockerComposeCmd -eq "docker-compose") {
        docker-compose exec -T gateway alembic upgrade head
    } else {
        docker compose exec -T gateway alembic upgrade head
    }
    Write-Host "Migrations applied successfully."
} catch {
    Write-Warning "Warning: Migration command failed or DB is not yet accepting connections. Please check logs."
}

Write-Host "`n=================================================" -ForegroundColor Cyan
Write-Host "Deployment Complete! 🚀" -ForegroundColor Green
Write-Host "Gateway URL:   http://localhost:8000"
Write-Host "API Docs:      http://localhost:8000/docs"
Write-Host "Health Check:  http://localhost:8000/health"
Write-Host "Grafana:       Import 'grafana-dashboard.json' into your deployment"
Write-Host "=================================================" -ForegroundColor Cyan
