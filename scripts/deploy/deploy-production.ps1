<#
.SYNOPSIS
    Production deployment script for Algotrading Platform

.DESCRIPTION
    Handles:
    - Environment validation
    - Database migrations
    - Docker build and deployment
    - Health check verification
    - Rollback support

.PARAMETER Action
    Action to perform: deploy, rollback, status, migrate, build

.PARAMETER Environment
    Target environment: production, staging

.EXAMPLE
    .\deploy-production.ps1 -Action deploy -Environment production
#>

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("deploy", "rollback", "status", "migrate", "build", "validate")]
    [string]$Action,
    
    [Parameter(Mandatory=$false)]
    [ValidateSet("production", "staging")]
    [string]$Environment = "staging",
    
    [Parameter(Mandatory=$false)]
    [string]$Version = "latest",
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipValidation,
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipMigrations,
    
    [Parameter(Mandatory=$false)]
    [switch]$DryRun
)

# =============================================================================
# Configuration
# =============================================================================

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = $ScriptDir
$ComposeFile = Join-Path $ProjectRoot "docker-compose.production.yml"
$EnvFile = Join-Path $ProjectRoot ".env.$Environment"

# Colors for output
function Write-Info { param($Message) Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-Success { param($Message) Write-Host "[SUCCESS] $Message" -ForegroundColor Green }
function Write-Warning { param($Message) Write-Host "[WARNING] $Message" -ForegroundColor Yellow }
function Write-Error { param($Message) Write-Host "[ERROR] $Message" -ForegroundColor Red }

# =============================================================================
# Validation Functions
# =============================================================================

function Test-Prerequisites {
    Write-Info "Checking prerequisites..."
    
    # Check Docker
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        throw "Docker is not installed or not in PATH"
    }
    
    # Check Docker Compose
    $compose = docker compose version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose is not available"
    }
    
    # Check environment file
    if (-not (Test-Path $EnvFile)) {
        throw "Environment file not found: $EnvFile"
    }
    
    Write-Success "Prerequisites check passed"
}

function Test-EnvironmentVariables {
    Write-Info "Validating environment variables..."
    
    # Load environment file
    $envContent = Get-Content $EnvFile | Where-Object { $_ -match "^[^#].*=.*" }
    $envVars = @{}
    
    foreach ($line in $envContent) {
        $parts = $line -split "=", 2
        if ($parts.Count -eq 2) {
            $envVars[$parts[0].Trim()] = $parts[1].Trim()
        }
    }
    
    # Required variables
    $required = @(
        "DB_PASSWORD",
        "JWT_SECRET"
    )
    
    if ($Environment -eq "production") {
        $required += @(
            "ALPACA_API_KEY",
            "ALPACA_SECRET_KEY"
        )
    }
    
    $missing = @()
    foreach ($var in $required) {
        if (-not $envVars.ContainsKey($var) -or [string]::IsNullOrEmpty($envVars[$var])) {
            $missing += $var
        }
    }
    
    if ($missing.Count -gt 0) {
        throw "Missing required environment variables: $($missing -join ', ')"
    }
    
    # Security validation
    $jwtSecret = $envVars["JWT_SECRET"]
    if ($jwtSecret.Length -lt 32) {
        Write-Warning "JWT_SECRET is shorter than recommended 32 characters"
    }
    
    if ($jwtSecret -eq "development-secret") {
        throw "Cannot use development JWT secret in $Environment"
    }
    
    Write-Success "Environment validation passed"
}

# =============================================================================
# Deployment Functions
# =============================================================================

function Invoke-Build {
    Write-Info "Building Docker images..."
    
    $buildArgs = @(
        "compose",
        "-f", $ComposeFile,
        "--env-file", $EnvFile,
        "build",
        "--no-cache"
    )
    
    if ($DryRun) {
        Write-Info "[DRY RUN] Would execute: docker $($buildArgs -join ' ')"
        return
    }
    
    & docker @buildArgs
    
    if ($LASTEXITCODE -ne 0) {
        throw "Docker build failed"
    }
    
    Write-Success "Docker images built successfully"
}

function Invoke-Migrations {
    Write-Info "Running database migrations..."
    
    if ($SkipMigrations) {
        Write-Info "Skipping migrations (--SkipMigrations flag)"
        return
    }
    
    if ($DryRun) {
        Write-Info "[DRY RUN] Would run alembic upgrade head"
        return
    }
    
    # Run migrations in container
    $migrateArgs = @(
        "compose",
        "-f", $ComposeFile,
        "--env-file", $EnvFile,
        "run", "--rm",
        "app",
        "alembic", "upgrade", "head"
    )
    
    & docker @migrateArgs
    
    if ($LASTEXITCODE -ne 0) {
        throw "Database migration failed"
    }
    
    Write-Success "Database migrations completed"
}

function Invoke-Deploy {
    Write-Info "Deploying application..."
    
    $deployArgs = @(
        "compose",
        "-f", $ComposeFile,
        "--env-file", $EnvFile,
        "up", "-d",
        "--remove-orphans"
    )
    
    if ($DryRun) {
        Write-Info "[DRY RUN] Would execute: docker $($deployArgs -join ' ')"
        return
    }
    
    & docker @deployArgs
    
    if ($LASTEXITCODE -ne 0) {
        throw "Deployment failed"
    }
    
    Write-Success "Application deployed"
}

function Test-HealthCheck {
    Write-Info "Waiting for health check..."
    
    if ($DryRun) {
        Write-Info "[DRY RUN] Would check health endpoint"
        return
    }
    
    $maxAttempts = 30
    $waitSeconds = 2
    $appPort = 8000
    
    for ($i = 1; $i -le $maxAttempts; $i++) {
        try {
            $response = Invoke-RestMethod -Uri "http://localhost:$appPort/health/live" -TimeoutSec 5
            if ($response.status -eq "alive") {
                Write-Success "Health check passed"
                return
            }
        }
        catch {
            Write-Info "Attempt $i/$maxAttempts - waiting..."
            Start-Sleep -Seconds $waitSeconds
        }
    }
    
    throw "Health check failed after $maxAttempts attempts"
}

function Invoke-Rollback {
    Write-Info "Rolling back deployment..."
    
    $rollbackArgs = @(
        "compose",
        "-f", $ComposeFile,
        "--env-file", $EnvFile,
        "down"
    )
    
    if ($DryRun) {
        Write-Info "[DRY RUN] Would execute: docker $($rollbackArgs -join ' ')"
        return
    }
    
    & docker @rollbackArgs
    
    Write-Success "Rollback completed"
}

function Get-Status {
    Write-Info "Getting deployment status..."
    
    $statusArgs = @(
        "compose",
        "-f", $ComposeFile,
        "--env-file", $EnvFile,
        "ps"
    )
    
    & docker @statusArgs
    
    Write-Info ""
    Write-Info "Container health:"
    
    $healthArgs = @(
        "ps", "--filter", "name=algotrading",
        "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    )
    
    & docker @healthArgs
}

# =============================================================================
# Main Execution
# =============================================================================

Write-Host ""
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "  Algotrading Platform Deployment" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Write-Host ""
Write-Info "Action: $Action"
Write-Info "Environment: $Environment"
Write-Info "Version: $Version"
if ($DryRun) { Write-Warning "Running in DRY RUN mode" }
Write-Host ""

try {
    switch ($Action) {
        "validate" {
            Test-Prerequisites
            Test-EnvironmentVariables
        }
        
        "build" {
            Test-Prerequisites
            Invoke-Build
        }
        
        "migrate" {
            Test-Prerequisites
            if (-not $SkipValidation) { Test-EnvironmentVariables }
            Invoke-Migrations
        }
        
        "deploy" {
            Test-Prerequisites
            if (-not $SkipValidation) { Test-EnvironmentVariables }
            Invoke-Build
            Invoke-Migrations
            Invoke-Deploy
            Test-HealthCheck
            Get-Status
        }
        
        "rollback" {
            Test-Prerequisites
            Invoke-Rollback
        }
        
        "status" {
            Test-Prerequisites
            Get-Status
        }
    }
    
    Write-Host ""
    Write-Success "Operation completed successfully!"
    Write-Host ""
}
catch {
    Write-Host ""
    Write-Error $_.Exception.Message
    Write-Host ""
    exit 1
}
