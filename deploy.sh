#!/bin/bash
# Deployment script for BRANCH 2.12 - Deploy Readiness
# Production deployment automation

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE=${NAMESPACE:-algotrading}
IMAGE_TAG=${IMAGE_TAG:-latest}
REGISTRY=${REGISTRY:-}

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if kubectl is installed
    if ! command -v kubectl &> /dev/null; then
        error "kubectl is not installed or not in PATH"
    fi
    
    # Check if docker is installed (for build)
    if ! command -v docker &> /dev/null; then
        error "docker is not installed or not in PATH"
    fi
    
    # Check if kustomize is available
    if ! kubectl kustomize --help &> /dev/null; then
        error "kubectl kustomize is not available"
    fi
    
    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        error "Cannot connect to Kubernetes cluster"
    fi
    
    log "Prerequisites check passed"
}

build_image() {
    log "Building Docker image..."
    
    local image_name="algotrading/api"
    if [[ -n "$REGISTRY" ]]; then
        image_name="$REGISTRY/algotrading/api"
    fi
    
    docker build -t "$image_name:$IMAGE_TAG" .
    
    if [[ -n "$REGISTRY" ]]; then
        log "Pushing image to registry..."
        docker push "$image_name:$IMAGE_TAG"
    fi
    
    log "Image build completed: $image_name:$IMAGE_TAG"
}

create_secrets() {
    log "Creating secrets (if not exist)..."
    
    # Check if secrets exist
    if kubectl get secret algotrading-secrets -n "$NAMESPACE" &> /dev/null; then
        warn "Secret 'algotrading-secrets' already exists, skipping creation"
    else
        # Create from template (requires manual editing)
        kubectl apply -f k8s/namespace.yaml
        warn "Please manually create secrets based on templates in k8s/namespace.yaml"
        warn "Secrets needed: algotrading-secrets, alpaca-secrets, postgres-secrets"
        
        # Wait for user to create secrets
        read -p "Press Enter after creating all required secrets..."
    fi
}

deploy_infrastructure() {
    log "Deploying infrastructure components..."
    
    # Apply namespace and base resources
    kubectl apply -f k8s/namespace.yaml
    
    # Deploy PostgreSQL
    log "Deploying PostgreSQL..."
    kubectl apply -f k8s/postgres.yaml
    
    # Deploy Redis
    log "Deploying Redis..."
    kubectl apply -f k8s/redis.yaml
    
    # Deploy OpenTelemetry Collector
    log "Deploying OpenTelemetry Collector..."
    kubectl apply -f k8s/otel-collector.yaml
    
    # Deploy Prometheus
    log "Deploying Prometheus..."
    kubectl apply -f k8s/prometheus.yaml
    
    # Wait for infrastructure to be ready
    log "Waiting for infrastructure to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/postgres -n "$NAMESPACE" || true
    kubectl wait --for=condition=available --timeout=300s deployment/redis -n "$NAMESPACE" || true
    kubectl wait --for=condition=available --timeout=300s deployment/otel-collector -n "$NAMESPACE" || true
    kubectl wait --for=condition=available --timeout=300s deployment/prometheus -n "$NAMESPACE" || true
    
    log "Infrastructure deployment completed"
}

deploy_application() {
    log "Deploying application..."
    
    # Update image tag in kustomization
    cd k8s
    kustomize edit set image algotrading/api="algotrading/api:$IMAGE_TAG"
    cd ..
    
    # Apply with kustomize
    kubectl apply -k k8s/
    
    # Wait for deployment to be ready
    log "Waiting for application to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/algotrading-api -n "$NAMESPACE"
    
    log "Application deployment completed"
}

health_check() {
    log "Performing health checks..."
    
    # Get service endpoint
    local service_ip
    service_ip=$(kubectl get svc algotrading-api-service -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}')
    
    # Check health endpoints
    kubectl run health-check --rm -i --restart=Never --image=curlimages/curl -- \
        curl -f "http://$service_ip:8000/healthz" || warn "Health check failed"
    
    kubectl run readiness-check --rm -i --restart=Never --image=curlimages/curl -- \
        curl -f "http://$service_ip:8000/readyz" || warn "Readiness check failed"
    
    log "Health checks completed"
}

show_status() {
    log "Deployment Status:"
    echo
    
    # Show all resources
    kubectl get all -n "$NAMESPACE"
    echo
    
    # Show service endpoints
    log "Service endpoints:"
    kubectl get svc -n "$NAMESPACE"
    echo
    
    # Show ingress (if exists)
    if kubectl get ingress -n "$NAMESPACE" &> /dev/null; then
        log "Ingress configuration:"
        kubectl get ingress -n "$NAMESPACE"
        echo
    fi
    
    # Show logs from API pods
    log "Recent API logs:"
    kubectl logs -l app=algotrading-api -n "$NAMESPACE" --tail=20
}

rollback() {
    warn "Rolling back deployment..."
    kubectl rollout undo deployment/algotrading-api -n "$NAMESPACE"
    kubectl wait --for=condition=available --timeout=300s deployment/algotrading-api -n "$NAMESPACE"
    log "Rollback completed"
}

cleanup() {
    warn "Cleaning up deployment..."
    kubectl delete namespace "$NAMESPACE" --ignore-not-found=true
    log "Cleanup completed"
}

main() {
    local command="${1:-deploy}"
    
    case "$command" in
        "check")
            check_prerequisites
            ;;
        "build")
            check_prerequisites
            build_image
            ;;
        "secrets")
            create_secrets
            ;;
        "infra")
            check_prerequisites
            create_secrets
            deploy_infrastructure
            ;;
        "app")
            check_prerequisites
            deploy_application
            health_check
            ;;
        "deploy")
            check_prerequisites
            build_image
            create_secrets
            deploy_infrastructure
            deploy_application
            health_check
            show_status
            ;;
        "status")
            show_status
            ;;
        "rollback")
            rollback
            ;;
        "cleanup")
            cleanup
            ;;
        *)
            echo "Usage: $0 {check|build|secrets|infra|app|deploy|status|rollback|cleanup}"
            echo
            echo "Commands:"
            echo "  check    - Check prerequisites"
            echo "  build    - Build and optionally push Docker image"
            echo "  secrets  - Create Kubernetes secrets"
            echo "  infra    - Deploy infrastructure components"
            echo "  app      - Deploy application"
            echo "  deploy   - Full deployment (build + infra + app)"
            echo "  status   - Show deployment status"
            echo "  rollback - Rollback to previous version"
            echo "  cleanup  - Delete all resources"
            echo
            echo "Environment variables:"
            echo "  NAMESPACE   - Kubernetes namespace (default: algotrading)"
            echo "  IMAGE_TAG   - Docker image tag (default: latest)"
            echo "  REGISTRY    - Docker registry (optional)"
            exit 1
            ;;
    esac
}

main "$@"
