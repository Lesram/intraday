# PowerShell deployment script for BRANCH 2.12 - Deploy Readiness
# Production deployment automation for Windows

param(
    [Parameter(Position=0)]
    [ValidateSet("check", "build", "secrets", "infra", "app", "deploy", "status", "rollback", "cleanup")]
    [string]$Command = "deploy",

    [string]$Namespace = "algotrading",
    [string]$ImageTag = "latest",
    [string]$Registry = ""
)

$ErrorActionPreference = "Stop"

# Colors for output
$Colors = @{
    Red = [ConsoleColor]::Red
    Green = [ConsoleColor]::Green
    Yellow = [ConsoleColor]::Yellow
    White = [ConsoleColor]::White
}

function Write-Log {
    param([string]$Message, [ConsoleColor]$Color = $Colors.Green)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] $Message" -ForegroundColor $Color
}

function Write-Warning {
    param([string]$Message)
    Write-Log "WARNING: $Message" -Color $Colors.Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Log "ERROR: $Message" -Color $Colors.Red
    exit 1
}

function Test-Prerequisites {
    Write-Log "Checking prerequisites..."

    # Check if kubectl is installed
    try {
        $null = kubectl version --client 2>$null
    } catch {
        Write-Error "kubectl is not installed or not in PATH"
    }

    # Check if docker is installed
    try {
        $null = docker --version 2>$null
    } catch {
        Write-Error "docker is not installed or not in PATH"
    }

    # Check cluster connectivity
    try {
        $null = kubectl cluster-info 2>$null
    } catch {
        Write-Error "Cannot connect to Kubernetes cluster"
    }

    Write-Log "Prerequisites check passed"
}

function Build-Image {
    Write-Log "Building Docker image..."

    $imageName = "algotrading/api"
    if ($Registry) {
        $imageName = "$Registry/algotrading/api"
    }

    docker build -t "${imageName}:${ImageTag}" .
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker build failed"
    }

    if ($Registry) {
        Write-Log "Pushing image to registry..."
        docker push "${imageName}:${ImageTag}"
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Docker push failed"
        }
    }

    Write-Log "Image build completed: ${imageName}:${ImageTag}"
}

function New-Secrets {
    Write-Log "Creating secrets (if not exist)..."

    # Check if secrets exist
    $secretExists = $false
    try {
        kubectl get secret algotrading-secrets -n $Namespace 2>$null
        $secretExists = $true
    } catch {}

    if ($secretExists) {
        Write-Warning "Secret 'algotrading-secrets' already exists, skipping creation"
    } else {
        # Create namespace first
        kubectl apply -f k8s/namespace.yaml

        Write-Warning "Please manually create secrets based on templates in k8s/namespace.yaml"
        Write-Warning "Secrets needed: algotrading-secrets, alpaca-secrets, postgres-secrets"

        # Wait for user to create secrets
        Read-Host "Press Enter after creating all required secrets..."
    }
}

function Deploy-Infrastructure {
    Write-Log "Deploying infrastructure components..."

    # Apply namespace and base resources
    kubectl apply -f k8s/namespace.yaml

    # Deploy PostgreSQL
    Write-Log "Deploying PostgreSQL..."
    kubectl apply -f k8s/postgres.yaml

    # Deploy Redis
    Write-Log "Deploying Redis..."
    kubectl apply -f k8s/redis.yaml

    # Deploy OpenTelemetry Collector
    Write-Log "Deploying OpenTelemetry Collector..."
    kubectl apply -f k8s/otel-collector.yaml

    # Deploy Prometheus
    Write-Log "Deploying Prometheus..."
    kubectl apply -f k8s/prometheus.yaml

    # Wait for infrastructure to be ready
    Write-Log "Waiting for infrastructure to be ready..."
    kubectl wait --for=condition=available --timeout=300s statefulset/postgres -n $Namespace
    kubectl wait --for=condition=available --timeout=300s deployment/redis -n $Namespace
    kubectl wait --for=condition=available --timeout=300s deployment/otel-collector -n $Namespace
    kubectl wait --for=condition=available --timeout=300s deployment/prometheus -n $Namespace

    Write-Log "Infrastructure deployment completed"
}

function Deploy-Application {
    Write-Log "Deploying application..."

    # Update image tag in kustomization
    Set-Location k8s
    kustomize edit set image "algotrading/api=algotrading/api:$ImageTag"
    Set-Location ..

    # Apply with kustomize
    kubectl apply -k k8s/

    # Wait for deployment to be ready
    Write-Log "Waiting for application to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/algotrading-api -n $Namespace

    Write-Log "Application deployment completed"
}

function Test-Health {
    Write-Log "Performing health checks..."

    # Get service endpoint
    $serviceIP = kubectl get svc algotrading-api-service -n $Namespace -o jsonpath='{.spec.clusterIP}'

    # Check health endpoints
    try {
        kubectl run health-check --rm -i --restart=Never --image=curlimages/curl -- curl -f "http://${serviceIP}:8000/healthz"
    } catch {
        Write-Warning "Health check failed"
    }

    try {
        kubectl run readiness-check --rm -i --restart=Never --image=curlimages/curl -- curl -f "http://${serviceIP}:8000/readyz"
    } catch {
        Write-Warning "Readiness check failed"
    }

    Write-Log "Health checks completed"
}

function Show-Status {
    Write-Log "Deployment Status:"
    Write-Host ""

    # Show all resources
    kubectl get all -n $Namespace
    Write-Host ""

    # Show service endpoints
    Write-Log "Service endpoints:"
    kubectl get svc -n $Namespace
    Write-Host ""

    # Show ingress (if exists)
    try {
        kubectl get ingress -n $Namespace 2>$null
        Write-Log "Ingress configuration:"
        kubectl get ingress -n $Namespace
        Write-Host ""
    } catch {}

    # Show logs from API pods
    Write-Log "Recent API logs:"
    kubectl logs -l app=algotrading-api -n $Namespace --tail=20
}

function Invoke-Rollback {
    Write-Warning "Rolling back deployment..."
    kubectl rollout undo deployment/algotrading-api -n $Namespace
    kubectl wait --for=condition=available --timeout=300s deployment/algotrading-api -n $Namespace
    Write-Log "Rollback completed"
}

function Remove-Deployment {
    Write-Warning "Cleaning up deployment..."
    kubectl delete namespace $Namespace --ignore-not-found=true
    Write-Log "Cleanup completed"
}

# Main execution
switch ($Command) {
    "check" {
        Test-Prerequisites
    }
    "build" {
        Test-Prerequisites
        Build-Image
    }
    "secrets" {
        New-Secrets
    }
    "infra" {
        Test-Prerequisites
        New-Secrets
        Deploy-Infrastructure
    }
    "app" {
        Test-Prerequisites
        Deploy-Application
        Test-Health
    }
    "deploy" {
        Test-Prerequisites
        Build-Image
        New-Secrets
        Deploy-Infrastructure
        Deploy-Application
        Test-Health
        Show-Status
    }
    "status" {
        Show-Status
    }
    "rollback" {
        Invoke-Rollback
    }
    "cleanup" {
        Remove-Deployment
    }
    default {
        Write-Host @"
Usage: .\deploy.ps1 [Command] [Options]

Commands:
  check    - Check prerequisites
  build    - Build and optionally push Docker image
  secrets  - Create Kubernetes secrets
  infra    - Deploy infrastructure components
  app      - Deploy application
  deploy   - Full deployment (build + infra + app)
  status   - Show deployment status
  rollback - Rollback to previous version
  cleanup  - Delete all resources

Parameters:
  -Namespace   Kubernetes namespace (default: algotrading)
  -ImageTag    Docker image tag (default: latest)
  -Registry    Docker registry (optional)

Examples:
  .\deploy.ps1 deploy -ImageTag "v1.0.0"
  .\deploy.ps1 build -Registry "myregistry.com"
  .\deploy.ps1 status
"@
    }
}
